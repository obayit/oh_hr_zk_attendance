# -*- coding: utf-8 -*-
###################################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#    Copyright (C) 2018-TODAY Cybrosys Technologies(<http://www.cybrosys.com>).
#    Author: cybrosys(<https://www.cybrosys.com>)
#
#    This program is free software: you can modify
#    it under the terms of the GNU Affero General Public License (AGPL) as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###################################################################################
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
    device_id = fields.Char(string='Biometric Device ID')

class ZkIssue(models.Model):
    _name = 'hr.zk.issue'
    _description = "Issues with attendance machine"

    machine_id = fields.Many2one('zk.machine', string='Biometric Device ID')
    employee_id = fields.Many2one('hr.employee', string='Employee')
    issue_type = fields.Selection([('still_in', "Didn't check out"),
                                    ('unknown', 'Unknown Issue')],
                                  string='Issue Type')
    datetime = fields.Datetime('Related Time')
    error_message = fields.Text('Error Message')

class ZkMachine(models.Model):
    _name = 'zk.machine'
    _description = 'ZK Machine Configuration'

    name = fields.Char(string='Machine IP', required=True)
    port_no = fields.Integer(string='Port No', required=True)
    is_udp = fields.Boolean('Is using UDP', default=False)
    address_id = fields.Many2one('res.partner', string='Address')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id.id)
    password = fields.Integer('Password')
    issue_ids = fields.One2many('hr.zk.issue', 'machine_id', 'Issues')
    issue_count = fields.Integer('Issues Count', compute='_compute_issue_count')

    tz = fields.Selection(_tz_get, string='Timezone', default=lambda self: self._context.get('tz'), required=True)
    
    def get_user_time(self, target_date):
        from_date = fields.Datetime.from_string(target_date)
        user_tz = self.env.user.tz
        if not user_tz:
            user_tz = self._context.get('tz')
        if not user_tz:
            user_tz = pytz.utc
        return fields.Datetime.to_string(pytz.timezone(self.tz).localize(from_date, is_dst=None).astimezone(pytz.timezone(user_tz) or pytz.utc))

    def _compute_issue_count(self):
        for r in self:
            r.issue_count = len(r.issue_ids)

    def clear_attendance(self):
        # todo
        for info in self:
            try:
                zk = ZK(info.name, port=info.port_no, timeout=5, password=info.password, force_udp=info.is_udp, ommit_ping=False)
                conn = zk.connect()
                if conn:
                    clear_data = zk.get_attendance()
                    if clear_data:
                        zk.clear_attendance()
                        self._cr.execute("""delete from zk_machine_attendance""")
                    else:
                        raise UserError(_('Unable to get the attendance log, please try again later.'))
                else:
                    raise UserError(_('Unable to connect, please check the parameters and network connections.'))
            except:
                raise ValidationError('Warning !!! Machine is not connected')

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
                converted_time = info.get_user_time(each.timestamp)
                biometric_employee_id = self.env['hr.biometric.employee'].search(
                    [('machine_id', '=', info.id), ('device_id', '=', each.user_id)])
                employee_id = biometric_employee_id and biometric_employee_id.employee_id or False
                if not employee_id:
                    continue

                duplicate_atten_ids = zk_attendance.search(
                    [('machine_id', '=', info.id), ('device_id', '=', each.user_id) 
                    ,('punching_time', '=', converted_time)
                    ])
                if duplicate_atten_ids:
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
                if each.punch == CHECK_IN and not att_var:
                    try:
                        att_obj.create({'employee_id': employee_id.id,
                                        'check_in': converted_time})
                    except Exception as ex: 
                        issue_obj.create({
                            'employee_id': employee_id.id,
                            'issue_type': 'still_in',
                            'machine_id': info.id,
                            'datetime': converted_time,
                            'error_message': ex,
                            })
                        continue
                elif each.punch == CHECK_OUT:  # check-out
                    try:
                        att_var.write({'check_out': converted_time})
                    except Exception as ex: 
                        issue_obj.create({
                            'employee_id': employee_id.id,
                            'issue_type': 'unknown',
                            'machine_id': info.id,
                            'datetime': converted_time,
                            'error_message': ex,
                            })
                        continue
            zk.enable_device()
            zk.disconnect()
            return True
