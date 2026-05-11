# -*- coding: utf-8 -*-
# Part of Mehedi Hasan Rakib. See LICENSE file for full copyright and licensing details.
{

    'name': 'Health Score v1',
    'version': '1.1',
    'summary': 'A simple tool to manage Customer Health Score.',
    'sequence': 2,
    'description':"""
        This module helps you to: 
        - Order frequency
        - Payment behavior
        - Support engagement
    """,
    'category':'Sales/CRM',
    'author':'MindSynth',
    'website': 'https://xyz.com',
    'license': 'LGPL-3',
    
    'depends':['base', 'mail', 'web', 'sale', 'account'],

   'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/res_config_settings_views.xml',
        'views/res_partner_views.xml',
        'views/menus.xml',                      
    ],


    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}