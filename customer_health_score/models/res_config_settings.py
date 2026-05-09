from odoo import models, fields, api
import datetime

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Thresholds
    x_healthy_threshold = fields.Integer(string="Healthy Threshold", config_parameter='customer_health.x_healthy_threshold', default=70)
    x_critical_threshold = fields.Integer(string="Critical Threshold", config_parameter='customer_health.x_critical_threshold', default=40)

    # Weights
    x_order_weight = fields.Float(string="Order Frequency Weight (%)", config_parameter='customer_health.x_order_weight', default=40.0)
    x_payment_weight = fields.Float(string="Payment Behavior Weight (%)", config_parameter='customer_health.x_payment_weight', default=35.0)

    # Analysis Settings
    x_analysis_days = fields.Integer(string="Analysis Period (Days)", config_parameter='customer_health.x_analysis_days', default=90)
    x_expected_order_gap = fields.Integer(string="Expected Order Gap (Days)", config_parameter='customer_health.x_expected_order_gap', default=30)

    # Payment Limits
    x_payment_good_limit = fields.Integer(string="Payment Good Limit (Days)", config_parameter='customer_health.x_payment_good_limit', default=30)
    x_payment_average_limit = fields.Integer(string="Payment Average Limit (Days)", config_parameter='customer_health.x_payment_average_limit', default=90)

    # Benchmark Info
    benchmark_info = fields.Char(string="Current Benchmark", compute="_compute_benchmark_info")

    @api.depends('x_analysis_days')
    def _compute_benchmark_info(self):
        for record in self:
            days = record.x_analysis_days or 90
            start_date = fields.Date.today() - datetime.timedelta(days=days)
            order_data = self.env['sale.order'].read_group(
                [('state', 'in', ('sale', 'done')), ('date_order', '>=', start_date)],
                ['partner_id'], ['partner_id'], orderby='partner_id_count desc', limit=1
            )
            if order_data:
                record.benchmark_info = f"{order_data[0]['partner_id'][1]} ({order_data[0]['partner_id_count']} Orders)"
            else:
                record.benchmark_info = "No orders found."

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        
        partners = self.env['res.partner'].search([])
        partners._compute_sub_scores()
        partners._compute_health_score()
        partners._compute_health_state()