from odoo import models, fields, api
import datetime

class ResPartner(models.Model):
    _inherit = 'res.partner'

    order_frequency_score = fields.Float(string="Order Frequency Score", compute="_compute_sub_scores", store=True)
    payment_behavior_score = fields.Float(string="Payment Behavior Score", compute="_compute_sub_scores", store=True)
    revenue_trend_score = fields.Float(string="Revenue Trend Score", compute="_compute_sub_scores", store=True)
    health_score = fields.Float(string="Health Score", compute="_compute_health_score", store=True)
    last_health_compute = fields.Datetime(string="Last Health Update", readonly=True)

    health_state = fields.Selection([
        ('healthy', 'Healthy'),
        ('at_risk', 'At Risk'),
        ('critical', 'Critical')
    ], string="Health Status", compute="_compute_health_state", store=True)

    @api.depends('sale_order_ids', 'invoice_ids')
    def _compute_sub_scores(self):
        for partner in self:

            # Order Frequency
            order_count = len(partner.sale_order_ids)
            partner.order_frequency_score = min(order_count * 10, 100)

            # Payment Behavior
            overdue_invoices = partner.invoice_ids.filtered(
                lambda i: i.state == 'posted' and 
                i.payment_state in ('not_paid', 'partial') and 
                i.invoice_date_due and i.invoice_date_due < fields.Date.today()
            )
            if not partner.invoice_ids:
                partner.payment_behavior_score = 0
            else:
                partner.payment_behavior_score = 100 if not overdue_invoices else 30

            # Revenue Trend
            total_revenue = sum(partner.invoice_ids.mapped('amount_total'))
            partner.revenue_trend_score = min((total_revenue / 5000) * 10, 100) if total_revenue > 0 else 0

    @api.depends('order_frequency_score', 'payment_behavior_score', 'revenue_trend_score')
    def _compute_health_score(self):
        icp = self.env['ir.config_parameter'].sudo()
        w_order = float(icp.get_param('customer_health.x_order_weight') or 40.0)
        w_payment = float(icp.get_param('customer_health.x_payment_weight') or 35.0)
        w_revenue = float(icp.get_param('customer_health.x_revenue_weight') or 25.0)

        for partner in self:
            total_score = (
                (partner.order_frequency_score * (w_order / 100)) +
                (partner.payment_behavior_score * (w_payment / 100)) +
                (partner.revenue_trend_score * (w_revenue / 100))
            )
            partner.health_score = total_score

    @api.depends('health_score')
    def _compute_health_state(self):
        icp = self.env['ir.config_parameter'].sudo()
        crit_limit = float(icp.get_param('customer_health.x_critical_threshold') or 30.0)
        health_limit = float(icp.get_param('customer_health.x_healthy_threshold') or 80.0)

        for partner in self:
            if partner.health_score >= health_limit:
                partner.health_state = 'healthy'
            elif partner.health_score <= crit_limit:
                partner.health_state = 'critical'
            else:
                partner.health_state = 'at_risk'

    @api.model_create_multi
    def create(self, vals_list):
        records = super(ResPartner, self).create(vals_list)
        records._compute_health_score()
        records._compute_health_state()
        
        for record in records:
            if record.health_state == 'critical':
                record._create_critical_alert_activity()
        return records

    def write(self, vals):
        res = super(ResPartner, self).write(vals)
        if any(f in vals for f in ['sale_order_ids', 'invoice_ids', 'health_score']):
            for record in self:
                if record.health_state == 'critical':
                    record._create_critical_alert_activity()
        return res
 
    # Alert & Automation 
    def _create_critical_alert_activity(self):
        for partner in self:
            if not partner.id or isinstance(partner.id, models.NewId):
                continue

            activity_model = self.env['mail.activity']
            model_res_partner = self.env.ref('base.model_res_partner').id

            existing_activity = activity_model.search([
                ('res_id', '=', partner.id),
                ('res_model_id', '=', model_res_partner),
                ('summary', '=', 'Critical Health Alert: Immediate Action Required')
            ], limit=1)

            if not existing_activity:
                activity_model.create({
                    'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                    'note': f'The health score for {partner.name or "New Customer"} has dropped to {partner.health_score}. Please contact the customer.',
                    'summary': 'Critical Health Alert: Immediate Action Required',
                    'user_id': partner.user_id.id or self.env.user.id, 
                    'res_id': partner.id,
                    'res_model_id': model_res_partner,
                })