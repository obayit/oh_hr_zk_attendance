from odoo import tools
from odoo import models, fields, api, _
from pprint import pprint

class HrEmployee(models.Model):
    _inherit = "hr.employee"

    device_ids = fields.One2many('hr.biometric.employee', 'employee_id', 'Biometric Device ID')

    def get_time_period(self, datetime_str, tz_offset_number, states=['open']):
        self.ensure_one()
        datetime_date = fields.Datetime.from_string(datetime_str)
        contract_ids = self.sudo()._get_contracts(datetime_str, datetime_str, states)
        attendance_ids = contract_ids.mapped('resource_calendar_id.attendance_ids')
        closest_period = {'value': 99, 'type': False, 'period': False}
        period_counter = 0
        for att_id in attendance_ids.filtered(lambda r: r.dayofweek == str(datetime_date.weekday())).sorted('hour_from'):
            period_counter += 1
            hour_from = (att_id.hour_from - tz_offset_number)
            hour_to = (att_id.hour_to - tz_offset_number)
            computed_hour = datetime_date.hour + (datetime_date.minute / 60)
            diff_from = abs(computed_hour - hour_from)
            diff_to = abs(computed_hour - hour_to)
            diff_min = min(diff_from, diff_to)
            if diff_min < closest_period['value']:
                closest_period['value'] = diff_min
                closest_period['type'] = 'check_in' if diff_from < diff_to else 'check_out'
                closest_period['period'] = period_counter
        return closest_period

class HrEmployeeBiometricId(models.Model):
    _name = "hr.biometric.employee"
    _description = "Relation for Employee and Biometric Device"

    def _get_default_machine(self):
        machine_ids = self.env['zk.machine'].search([])
        if machine_ids:
            return machine_ids[0]
        else:
            return False

    employee_id = fields.Many2one('hr.employee', 'Employee', required=True)
    machine_id = fields.Many2one('zk.machine', 'Biometric Machine', required=True, default=_get_default_machine)
    device_id = fields.Char('Biometric Device ID')
