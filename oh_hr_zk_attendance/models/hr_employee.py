# -*- coding: utf-8 -*-
from odoo import tools
from odoo import models, fields, api, _

class HrEmployee(models.Model):
    _inherit = "hr.employee"

    device_ids = fields.One2many('hr.biometric.device', 'employee_id', string='Biometric Device ID')

class HrEmployeeBiometricId(models.Model):
    _name = "hr.biometric.device"
    _description = "Relation for Employee and Biometric Device"

    def _get_default_machine(self):
        machine_ids = self.env['zk.machine'].search([])
        if machine_ids:
            return machine_ids[0]
        else:
            return False

    employee_id = fields.Many2one('hr.employee', 'Employee', required=True)
    machine_id = fields.Many2one('zk.machine', 'Biometric Machine', required=True, default=_get_default_machine)
    device_id = fields.Char(string='Biometric Device ID')
