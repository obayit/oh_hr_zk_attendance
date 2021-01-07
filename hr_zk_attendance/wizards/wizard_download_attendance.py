import calendar
import datetime
from pprint import pprint

from odoo import models, fields, api

class DownloadAttendanceWizard(models.TransientModel):
    _name = 'hr.zk.download.wizard'
    _description = 'Download Attendance Wizard'

    def _get_default_date_from(self):
        return datetime.date.today().replace(day=1)

    def _get_default_date_to(self):
        today = datetime.date.today()
        return today.replace(day=calendar.monthrange(today.year, today.month)[1])

    date_from = fields.Date(required=True, default=_get_default_date_from)
    date_to = fields.Date(required=True, default=_get_default_date_to)
    duration_type = fields.Selection([
        ('this_month', 'This Month'),
        ('manual', 'Manual'),
    ], default='this_month')

    @api.onchange('duration_type')
    def onchange_duration_type(self):
        if not self.duration_type:
            return
        if self.duration_type == 'this_month':
            firstDay = datetime.date.today().replace(day=1)
            lastMonth = firstDay - datetime.timedelta(days=1)
            ir_config = self.env['ir.config_parameter'].sudo()
            self.date_from = lastMonth.replace(day=int(ir_config.get_param('hr_zk_attendance.month_start', 21)))
            self.date_to = firstDay.replace(day=int(ir_config.get_param('hr_zk_attendance.month_end', 20)))

    def download_data(self):
        self.env['zk.machine'].browse(self.env.context['active_id']).download_attendance(
            self.date_from, self.date_to
        )
