from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
   
    x_healthy_threshold = fields.Integer(string="Healthy Threshold", config_parameter='customer_health.x_healthy_threshold', default=80)
    x_critical_threshold = fields.Integer(string="Critical Threshold", config_parameter='customer_health.x_critical_threshold', default=40)

    def set_values(self):
        super().set_values()
        self.env['res.partner'].search([])._compute_sub_scores()