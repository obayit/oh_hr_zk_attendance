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

    def download_data(self):
        self.env['zk.machine'].browse(self.env.context['active_id']).download_attendance(
            self.date_from, self.date_to
        )
