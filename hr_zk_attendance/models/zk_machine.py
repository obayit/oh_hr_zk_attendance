import pytz
import sys
import datetime
import logging
import binascii
import pdb
import os
import re
from pprint import pprint, pformat
_logger = logging.getLogger(__name__)

from zk import ZK, const
from zk.attendance import Attendance
from struct import unpack
from odoo import api, fields, models
from odoo import _
from odoo.exceptions import UserError, ValidationError

from odoo.addons.base.models.res_partner import _tz_get

CHECK_IN = 0
CHECK_OUT = 1

class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    machine_id = fields.Many2one('zk.machine', 'Biometric Device')
    device_id = fields.Char('Biometric Device ID')

class ZkIssue(models.Model):
    _name = 'hr.zk.issue'
    _description = "Issues with attendance machine"

    machine_id = fields.Many2one('zk.machine', 'Biometric Device ID')
    employee_id = fields.Many2one('hr.employee', 'Employee')
    issue_type = fields.Selection([('missing_in', "Missing Check In"),
                                    ('missing_out', "Missing Check Out"),
                                    ('missing_schedule', "Missing Work Schedule")])
    datetime = fields.Datetime('Related Time')

class ZkMachine(models.Model):
    _name = 'zk.machine'
    _description = 'ZK Machine Configuration'

    name = fields.Char('Machine IP', required=True)
    port_no = fields.Integer('Port No.', required=True)
    is_udp = fields.Boolean('Is using UDP', default=False)
    address_id = fields.Many2one('res.partner', 'Address')
    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.user.company_id.id)
    password = fields.Integer()
    ignore_time = fields.Integer('Ignore Period', help="Ignore attendance record when the duration is shorter than this.", default=120)
    issue_ids = fields.One2many('hr.zk.issue', 'machine_id', 'Issues')
    issue_count = fields.Integer('Issues Count', compute='_compute_issue_count')

    tz = fields.Selection(_tz_get, 'Timezone', default=lambda self: self._context.get('tz'), required=True)
    tz_offset = fields.Char('Timezone Offset', compute='_compute_tz_offset', invisible=True)
    tz_offset_number = fields.Float('Timezone Offset Numeric', compute='_compute_tz_offset')

    @api.depends('tz')
    def _compute_tz_offset(self):
        for r in self:
            r.tz_offset = datetime.datetime.now(pytz.timezone(r.tz or 'GMT')).strftime('%z')
            device_now = datetime.datetime.now(pytz.timezone(r.tz or 'GMT'))
            r.tz_offset_number = device_now.utcoffset().total_seconds()/60/60
    
    def get_utc_time(self, target_date):
        # why? the machine sends the time, in it's timezone
        # but Odoo inside the code here only deals with UTC time
        from_date = fields.Datetime.from_string(target_date)
        return fields.Datetime.to_string(pytz.timezone(self.tz).localize(from_date, is_dst=None).astimezone(pytz.utc))

    def _compute_issue_count(self):
        for r in self:
            r.issue_count = len(r.issue_ids)

    def test_connection(self):
        for info in self:
            try:
                zk = ZK(info.name, port=info.port_no, timeout=5, password=info.password, force_udp=info.is_udp, ommit_ping=True)
                conn = zk.connect()
                if conn:
                    title = _("Connection Test Succeeded!")
                    message = _("Everything seems properly set up!")
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': title,
                            'message': message,
                            'type': 'info',
                            'sticky': False,
                        }
                    }
                else:
                    raise UserError(_('Unable to connect, please check the parameters and network connections.'))
            except:
                raise ValidationError(_('Warning !!! Machine is not connected'))

    @api.model
    def cron_download(self):
        _logger.info("++++++++++++ ZK Attendance Cron Executed ++++++++++++++++++++++")
        machines = self.env['zk.machine'].search([])
        for machine in machines :
            try:
                machine.download_attendance()
            except Exception as e:
                _logger.error("+++++++++++++++++++ ZK Attendance Mahcine Exception++++++++++++++++++++++\n{}".format(pformat(e)))

    def download_attendance(self):
        zk_attendance = self.env['zk.machine.attendance']
        att_obj = self.env['hr.attendance']
        issue_obj = self.env['hr.zk.issue']
        for info in self:
            zk = ZK(info.name, port=info.port_no, timeout=5, password=info.password, force_udp=info.is_udp, ommit_ping=True)
            conn = zk.connect()
            if not conn:
                raise UserError(_('Unable to connect, please check the parameters and network connections.'))

            conn.disable_device()  # safe to use. The device will re-enable itself automatically if the connection is closed (or this method might not be working at all)
            try:
                attendance = conn.get_attendance()
            except Exception as e:
                _logger.info("+++++++++++++++++++ ZK Attendance Mahcine Exception++++++++++++++++++++++\n{}".format(pformat(e)))
                attendance = False
            if not attendance:
                raise UserError(_('Unable to get the attendance log (may be empty!), please try again later.'))
            issue_obj.search([('machine_id', '=', info.id)]).unlink()

            for each in attendance:
                converted_time = info.get_utc_time(each.timestamp)
                if converted_time[5:7] != '07':
                    continue
                biometric_employee_id = self.env['hr.biometric.employee'].search(
                    [('machine_id', '=', info.id), ('device_id', '=', each.user_id)])
                employee_id = biometric_employee_id and biometric_employee_id.employee_id or False
                if not employee_id:
                    continue

                ##########################3
                if employee_id.id != 2:
                    continue

                duplicate_atten_ids = zk_attendance.search(
                    [('machine_id', '=', info.id), ('device_id', '=', each.user_id) 
                    ,('punching_time', '=', converted_time)
                    ])
                if duplicate_atten_ids:
                    continue

                print('# {} {}'.format(converted_time, employee_id.name))
                closes_period = employee_id.get_time_period(converted_time, info.tz_offset_number)
                if not closes_period['type']:
                    issue_obj.create({
                        'employee_id': employee_id.id,
                        'issue_type': 'missing_schedule',
                        'machine_id': info.id,
                        'datetime': converted_time,
                        })
                    continue

                zk_attendance.create({'employee_id': employee_id.id,
                                    'machine_id': info.id,
                                    'device_id': each.user_id,
                                    'attendance_type': '1',
                                    'punch_type': str(each.punch),
                                    'punching_time': converted_time,
                                    'address_id': info.address_id.id})
                att_var = att_obj.search([('employee_id', '=', employee_id.id),
                                            ('check_out', '=', False)])
                # if each.punch == CHECK_IN and not att_var:
                if not att_var: # assume check-in
                    if closes_period['type'] == 'check_in':
                        # normal
                        print('@ normal in')
                        att_obj.create({'employee_id': employee_id.id,
                                        'check_in': converted_time})
                    else:
                        print('@ abnormal in')
                        # problem: employee didn't check in
                        # meh = (fields.Datetime.from_string(converted_time) - datetime.timedelta(minutes=1))
                        abnormal_record = att_obj.create({'employee_id': employee_id.id,
                                        'check_in': converted_time})
                        abnormal_record.check_out = converted_time
                        issue_obj.create({
                            'employee_id': employee_id.id,
                            'issue_type': 'missing_in',
                            'machine_id': info.id,
                            'datetime': converted_time,
                            })
                # elif each.punch == CHECK_OUT:  # check-out
                else:  # assume check-out
                    time_diff = (fields.Datetime.from_string(converted_time) - att_var.check_in).seconds
                    if time_diff < info.ignore_time:
                        print('@ ignored')
                        continue
                    if closes_period['type'] == 'check_out':
                        print('@ normal out')
                        # normal
                        att_var.write({'check_out': converted_time})
                    else:
                        print('@ abnormal out')
                        att_var.check_out = att_var.check_in
                        abnormal_record = att_obj.create({'employee_id': employee_id.id,
                                        'check_in': converted_time})
                        abnormal_record.check_out = converted_time
                        # problem: employee didn't check in
                        issue_obj.create({
                            'employee_id': employee_id.id,
                            'issue_type': 'missing_out',
                            'machine_id': info.id,
                            'datetime': converted_time,
                            })
            zk.enable_device()
            zk.disconnect()
            return True
