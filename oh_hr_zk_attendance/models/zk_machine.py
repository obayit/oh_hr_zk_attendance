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
from pprint import pprint, pformat
_logger = logging.getLogger(__name__)

from zk import ZK, const
from zk.attendance import Attendance
from struct import unpack
from odoo import api, fields, models
from odoo import _
from odoo.exceptions import UserError, ValidationError



class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    device_id = fields.Char(string='Biometric Device ID')


class ZkMachine(models.Model):
    _name = 'zk.machine'
    _description = 'ZK Machine Configuration'

    name = fields.Char(string='Machine IP', required=True)
    port_no = fields.Integer(string='Port No', required=True)
    is_udp = fields.Boolean('Is using UDP', default=False)
    address_id = fields.Many2one('res.partner', string='Address')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id.id)
    password = fields.Integer('Password')

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
                _logger.error("+++++++++++++++++++ ZK Attendance Mahcine Exception++++++++++++++++++++++", e)
                pass

    def download_attendance(self):
        zk_attendance = self.env['zk.machine.attendance']
        att_obj = self.env['hr.attendance']
        issue_employees = self.env['hr.employee']
        for info in self:
            zk = ZK(info.name, port=info.port_no, timeout=5, password=info.password, force_udp=info.is_udp, ommit_ping=True)
            conn = zk.connect()
            if not conn:
                raise UserError(_('Unable to connect, please check the parameters and network connections.'))

            conn.disable_device()  # safe to use. The device will re-enable itself automatically if the connection is closed (or this method might not be working at all)
            try:
                attendance = conn.get_attendance()
            except Exception as e:
                _logger.info("+++++++++++++++++++ ZK Attendance Mahcine Exception++++++++++++++++++++++", e)
                attendance = False
            if not attendance:
                raise UserError(_('Unable to get the attendance log (may be empty!), please try again later.'))

            _logger.info('#### attendance records from machine')
            _logger.info(pformat(attendance))

            for each in attendance:
                employee_id = self.env['hr.employee'].search(
                    [('device_id', '=', each.user_id)])
                if not employee_id:
                    continue

                duplicate_atten_ids = zk_attendance.search(
                    [('device_id', '=', each.user_id), ('punching_time', '=', each.timestamp)])
                if duplicate_atten_ids:
                    continue

                each.timestamp = each.timestamp - datetime.timedelta(hours=2)
                zk_attendance.create({'employee_id': employee_id.id,
                                        'device_id': each.user_id,
                                        'attendance_type': '1',
                                        'punch_type': str(each.punch),
                                        'punching_time': each.timestamp,
                                        'address_id': info.address_id.id})
                att_var = att_obj.search([('employee_id', '=', employee_id.id),
                                            ('check_out', '=', False)])
                if each.punch == 0:  # check-in
                    if not att_var:
                        try:
                            att_obj.create({'employee_id': employee_id.id,
                                            'check_in': each.timestamp})
                        except:
                            _logger.info('#### Exception when creating hr.attendance record')
                            issue_employees |= employee_id
                if each.punch == 1:  # check-out
                    if len(att_var) == 1:
                        att_var.write({'check_out': each.timestamp})
                    else:
                        att_var1 = att_obj.search([('employee_id', '=', employee_id.id)])
                        if att_var1:
                            att_var1[-1].write({'check_out': each.timestamp})
            zk.enable_device()
            zk.disconnect()
            if issue_employees:
                warn_msg = _('The following employees encountered issues with fingerprint check in/check out.\n{}'.format(', '.join(issue_employees.mapped('name'))))
                return {'warning': {
                    'title': _('Warning'),
                    'message': warn_msg
                }
                }
            return True
