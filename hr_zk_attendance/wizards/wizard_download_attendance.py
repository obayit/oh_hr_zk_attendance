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
            lastMonthLastDay = firstDay - datetime.timedelta(days=1)
            ir_config = self.env['ir.config_parameter'].sudo()
            
            # make sure start day is in range of it's month
            day_start = int(ir_config.get_param('hr_zk_attendance.month_start', 21))
            day_start_ranage = calendar.monthrange(lastMonthLastDay.year, lastMonthLastDay.month)
            if not (day_start_ranage[0] <= day_start <= day_start_ranage[1]):
                day_start = day_start_ranage[0]
            self.date_from = lastMonthLastDay.replace(day=day_start)

            # make sure end day is in range of it's month
            day_end = int(ir_config.get_param('hr_zk_attendance.month_end', 20))
            day_end_ranage = calendar.monthrange(firstDay.year, firstDay.month)
            if not (day_end_ranage[0] <= day_end <= day_end_ranage[1]):
                day_end = day_end_ranage[1]
            self.date_to = firstDay.replace(day=day_end)

            # make sure the duration is not more than 31 days
            if (self.date_to - self.date_from).days > 31:
                self.date_to = lastMonthLastDay

    def download_data(self):
        self.env['zk.machine'].browse(self.env.context['active_id']).download_attendance(
            self.date_from, self.date_to
        )
