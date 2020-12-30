{
    'name': 'ZKteco Attendance Device Integration',
    'version': '13.0.1.0.0',
    'summary': """Integrating Biometric Device With HR Attendance and HR Contract""",
    'category': 'Human Resources',
    'author': 'Obay Abdelgadir',
    'website': "http://www.github.com/obayit",
    'depends': ['base_setup', 'hr_attendance', 'hr_contract'],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_employee_views.xml',
        'views/zk_issue_views.xml',
        'views/zk_machine_view.xml',
        'views/zk_machine_attendance_view.xml',
        'data/download_data.xml'

    ],
    'demo':[
        'data/attendance_demo.xml'
    ],
    'images': ['static/description/banner.jpg'],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
