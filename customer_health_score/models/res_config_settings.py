from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Thresholds
    x_healthy_threshold = fields.Integer(string="Healthy Threshold", config_parameter='customer_health.x_healthy_threshold', default=70)
    x_critical_threshold = fields.Integer(string="Critical Threshold", config_parameter='customer_health.x_critical_threshold', default=40)

    # Weights 
    x_order_weight = fields.Float(string="Order Frequency Weight (%)", config_parameter='customer_health.x_order_weight', default=40.0)
    x_payment_weight = fields.Float(string="Payment Behavior Weight (%)", config_parameter='customer_health.x_payment_weight', default=35.0)
    x_revenue_weight = fields.Float(string="Revenue Trend Weight (%)", config_parameter='customer_health.x_revenue_weight', default=25.0)

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        self.env['res.partner'].search([])._compute_health_state()