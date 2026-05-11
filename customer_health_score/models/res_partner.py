from odoo import models, fields, api
import datetime

class ResPartner(models.Model):
    _inherit = 'res.partner'

    order_frequency_score_text = fields.Char(string="Order Frequency Info", compute="_compute_sub_scores", store=True)

    payment_behavior_score = fields.Float(string="Payment Behavior Score", compute="_compute_sub_scores", store=True)
    payment_behavior_status = fields.Selection([
        ('good', 'Good'), ('poor', 'Poor'), 
    ], string="Payment Behavior", compute="_compute_sub_scores", store=True)

    payment_delay_info = fields.Char(string="Payment Details", compute="_compute_sub_scores", store=True)
    
    health_score = fields.Float(string="Rating", compute="_compute_sub_scores", store=True)
    health_state = fields.Selection([
        ('healthy', 'Healthy'), ('at_risk', 'At Risk'), ('critical', 'Critical'),
    ], string="Health Status", compute="_compute_health_state", store=True)

    last_health_compute = fields.Datetime(string="Last Health Update", readonly=True)

    @api.depends('sale_order_ids.state', 'invoice_ids.state', 'invoice_ids.payment_state', 'invoice_ids.invoice_date_due')
    def _compute_sub_scores(self):
        today = fields.Date.today()

        for partner in self:
            relevant_invoices = partner.invoice_ids.filtered(lambda i: i.state == 'posted' and i.move_type == 'out_invoice')
            
            overdue_invoices = relevant_invoices.filtered(lambda i: i.invoice_date_due and i.invoice_date_due < today and i.payment_state in ('not_paid', 'partial'))
            
            if overdue_invoices:
                partner.payment_behavior_status = 'poor'
                oldest_due = min(overdue_invoices.mapped('invoice_date_due'))
                delay = (today - oldest_due).days
                partner.payment_delay_info = f"{len(overdue_invoices)} Overdue | Max Delay: {delay} Days"
            else:
                partner.payment_behavior_status = 'good'
                partner.payment_delay_info = "No Overdue Invoices"

            total_inv = len(relevant_invoices)
            paid_inv = len(relevant_invoices.filtered(lambda i: i.payment_state == 'paid'))
            
            if total_inv > 0:
                calc_score = (paid_inv / total_inv) * 100
                partner.health_score = max(0, calc_score)
            else:
                partner.health_score = 100
            
            partner.payment_behavior_score = partner.health_score


            confirmed_orders = partner.sale_order_ids.filtered(lambda s: s.state in ('sale', 'done'))
            
            if len(confirmed_orders) > 1:
                dates = sorted([o.date_order.date() for o in confirmed_orders])
            else:
                
                dates = sorted([i.invoice_date for i in relevant_invoices if i.invoice_date])

            if len(dates) > 1:
                gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
                avg_gap = sum(gaps) / len(gaps)
                total_span = sum(gaps)
                partner.order_frequency_score_text = f"Avg Gap: {round(avg_gap, 1)} days | Span: {total_span} days"
            else:
                partner.order_frequency_score_text = f"Records: {len(dates)} | Need more data"

            partner.last_health_compute = fields.Datetime.now()

    @api.depends('health_score')
    def _compute_health_state(self):
        icp = self.env['ir.config_parameter'].sudo()
        healthy_threshold = int(icp.get_param('customer_health.x_healthy_threshold') or 80)
        critical_threshold = int(icp.get_param('customer_health.x_critical_threshold') or 40)
        
        for partner in self:
            if partner.health_score >= healthy_threshold:
                partner.health_state = 'healthy'
            elif partner.health_score <= critical_threshold:
                partner.health_state = 'critical'
            else:
                partner.health_state = 'at_risk'


    # --- Alerts & Automation ---
    @api.model_create_multi
    def create(self, vals_list):
        records = super(ResPartner, self).create(vals_list)
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

    def _create_critical_alert_activity(self):
        for partner in self:
            if not partner.id or isinstance(partner.id, models.NewId):
                continue
            activity_model = self.env['mail.activity']
            model_id = self.env.ref('base.model_res_partner').id
            
            existing = activity_model.search([
                ('res_id', '=', partner.id),
                ('res_model_id', '=', model_id),
                ('summary', '=', 'Critical Health Alert: Immediate Action Required')
            ], limit=1)

            if not existing:
                activity_model.create({
                    'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                    'summary': 'Critical Health Alert: Immediate Action Required',
                    'note': f'The health score for {partner.name} has dropped to {partner.health_score}%.',
                    'res_id': partner.id,
                    'res_model_id': model_id,
                    'user_id': partner.user_id.id or self.env.user.id,
                    'date_deadline': fields.Date.today(),
                })

class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        res = super(AccountMove, self).action_post()
        for move in self:
            if move.partner_id:
                move.partner_id._compute_sub_scores()
        return res

    def write(self, vals):
        res = super(AccountMove, self).write(vals)
        if any(f in vals for f in ['payment_state', 'invoice_date_due', 'state']):
            for move in self:
                if move.partner_id:
                    move.partner_id._compute_sub_scores()
        return res

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()
        for order in self:
            if order.partner_id:
                order.partner_id._compute_sub_scores()
        return res