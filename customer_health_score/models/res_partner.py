from odoo import models, fields, api
import datetime

class ResPartner(models.Model):
    _inherit = 'res.partner'

    order_frequency_score = fields.Char(string="Order Frequency Score", compute="_compute_sub_scores", store=True)
    order_frequency_score_text = fields.Char(string="Order Frequency Info", compute="_compute_sub_scores", store=True)

    payment_behavior_status = fields.Selection([
        ('good', 'Good'),
        ('average', 'Average'),
        ('poor', 'Poor')
    ], string="Payment Behavior", compute="_compute_sub_scores", store=True)

    payment_behavior_score = fields.Float(string="Payment Behavior Score", compute="_compute_sub_scores", store=True)
    payment_delay_info = fields.Char(string="Payment Delay Details", compute="_compute_sub_scores", store=True)

    health_score = fields.Float(string="Rating", compute="_compute_health_score", store=True)
    last_health_compute = fields.Datetime(string="Last Health Update", readonly=True)

    health_state = fields.Selection([
        ('healthy', 'Healthy'),
        ('at_risk', 'At Risk'),
        ('critical', 'Critical')
    ], string="Health Status", compute="_compute_health_state", store=True)

    @api.depends('sale_order_ids', 'invoice_ids')
    def _compute_sub_scores(self):
        icp = self.env['ir.config_parameter'].sudo()
        days = int(icp.get_param('customer_health.x_analysis_days') or 90)
        expected_gap = int(icp.get_param('customer_health.x_expected_order_gap') or 30)
        start_date = fields.Date.today() - datetime.timedelta(days=days)

        good_limit = int(icp.get_param('customer_health.x_payment_good_limit') or 30)
        avg_limit = int(icp.get_param('customer_health.x_payment_average_limit') or 90)

        for partner in self:

            # 1. Order Frequency Score
            orders = partner.sale_order_ids.filtered(
                lambda s: s.state in ('sale', 'done') and s.date_order.date() >= start_date
            ).sorted('date_order')
            
            if len(orders) > 1:
                gaps = []
                for i in range(len(orders) - 1):
                    gap = (orders[i+1].date_order.date() - orders[i].date_order.date()).days
                    gaps.append(gap)
                avg_gap = sum(gaps) / len(gaps)
                partner.order_frequency_score_text = f"[{int(avg_gap)} Days]"
                partner.order_frequency_score = max(0, min(100, (expected_gap / avg_gap) * 100)) if avg_gap > 0 else 0
            else:
                partner.order_frequency_score_text = "[No Sufficient Data]"
                partner.order_frequency_score = 0

            # 2. Payment Behavior Score 
            all_posted = partner.invoice_ids.filtered(lambda i: i.state == 'posted')
            overdue_invoices= all_posted.filtered(
                lambda i: i.payment_state in ('not_paid', 'partial') and 
                i.invoice_date_due and i.invoice_date_due < fields.Date.today()
            )
            
            oldest_due_days = 0
            if overdue_invoices:
                oldest_due_date = min(overdue_invoices.mapped('invoice_date_due'))
                oldest_due_days = (fields.Date.today() - oldest_due_date).days

            if not all_posted:
                partner.payment_behavior_status = 'good'
                partner.payment_behavior_score = 100
                partner.payment_delay_info = "No Invoice Found"
            else:
                if oldest_due_days == 0:
                    partner.payment_behavior_status = 'good'
                    partner.payment_behavior_score = 100
                    partner.payment_delay_info = "No Overdue"
                elif oldest_due_days <= good_limit:
                    partner.payment_behavior_status = 'good'
                    partner.payment_behavior_score = 80
                    partner.payment_delay_info = f"Oldest Due: {oldest_due_days} Days"
                elif oldest_due_days <= avg_limit:
                    partner.payment_behavior_status = 'average'
                    partner.payment_behavior_score = 50
                    partner.payment_delay_info = f"Oldest Due: {oldest_due_days} Days"
                else:
                    partner.payment_behavior_status = 'poor'
                    partner.payment_behavior_score = 20
                    partner.payment_delay_info = f"Critical Due: {oldest_due_days} Days"


    @api.depends('order_frequency_score', 'payment_behavior_score')
    def _compute_health_score(self):
        icp = self.env['ir.config_parameter'].sudo()
        w_order = float(icp.get_param('customer_health.x_order_weight') or 40.0)
        w_payment = float(icp.get_param('customer_health.x_payment_weight') or 35.0)

        for partner in self:
            total_score = (
                (partner.order_frequency_score * (w_order / 100)) +
                (partner.payment_behavior_score * (w_payment / 100)) 
            )
            partner.health_score = total_score
            partner.last_health_compute = fields.Datetime.now()

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