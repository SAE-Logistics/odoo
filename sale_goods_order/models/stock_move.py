from datetime import datetime, time

from odoo import api, fields, models, _
from odoo.tools.float_utils import float_round
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = "stock.move"

    consumption_source_picking_id = fields.Many2one(
        "stock.picking",
        string="Consumption Source Picking",
        help="Original picking for which this move represents material consumption.",
    )
    container_type_id = fields.Many2one(
        "stock.package.type",
        string="Container Type",
        default=lambda self: self._default_container_type_id(),
        copy=True,
    )
    container_count = fields.Integer(
        string="No. of Containers",
        default=0,
        copy=True,
    )

    @api.model
    def _default_container_type_id(self):
        parameter = self.env["ir.config_parameter"].sudo().get_param(
            "sale_gto.default_container_type_id"
        )
        return int(parameter) if parameter else False

    @api.model_create_multi
    def create(self, vals_list):
        default_container_type_id = self._default_container_type_id()
        for vals in vals_list:
            if not vals.get("container_type_id") and default_container_type_id:
                vals["container_type_id"] = default_container_type_id
        return super().create(vals_list)

    def write(self, vals):
        if {"container_type_id", "container_count"} & set(vals):
            locked_moves = self.filtered(lambda move: move.state in ("done", "cancel"))
            if locked_moves:
                raise UserError(
                    _(
                        "Container Type and No. of Containers cannot be changed on done or cancelled stock moves."
                    )
                )
        return super().write(vals)

    def _get_container_partner(self):
        self.ensure_one()
        partner = self.picking_id.partner_id
        return partner.commercial_partner_id if partner else self.env["res.partner"]

    def _get_effective_container_locations(self):
        self.ensure_one()
        done_lines = self.move_line_ids.filtered(lambda line: line.quantity > 0)
        if not done_lines:
            return [(self.location_id, self.location_dest_id, float(self.container_count or 0))]

        unique_pairs = {
            (line.location_id.id, line.location_dest_id.id)
            for line in done_lines
        }
        if len(unique_pairs) == 1:
            line = done_lines[0]
            return [(line.location_id, line.location_dest_id, float(self.container_count or 0))]

        total_qty = sum(done_lines.mapped("quantity"))
        if total_qty <= 0:
            return [(self.location_id, self.location_dest_id, float(self.container_count or 0))]

        flows = []
        remaining_containers = float(self.container_count or 0)
        last_index = len(done_lines) - 1
        for index, line in enumerate(done_lines):
            if index == last_index:
                line_containers = remaining_containers
            else:
                line_containers = float_round(
                    (self.container_count or 0) * line.quantity / total_qty,
                    precision_digits=6,
                )
                remaining_containers -= line_containers
            flows.append((line.location_id, line.location_dest_id, line_containers))
        return flows

    @api.model
    def _iter_container_impacts(
        self,
        date_from=False,
        date_to=False,
        partner_id=False,
        location_id=False,
        container_type_id=False,
    ):
        domain = [
            ("state", "=", "done"),
            ("container_count", ">", 0),
            ("container_type_id", "!=", False),
        ]
        if date_from:
            date_from_dt = datetime.combine(date_from, time.min)
            domain.append(("date", ">=", fields.Datetime.to_string(date_from_dt)))
        if date_to:
            date_to_dt = datetime.combine(date_to, time.max)
            domain.append(("date", "<=", fields.Datetime.to_string(date_to_dt)))
        if container_type_id:
            domain.append(("container_type_id", "=", container_type_id))

        for move in self.search(domain):
            move_partner = move._get_container_partner()
            if partner_id and move_partner.id != partner_id:
                continue

            for source_location, dest_location, quantity in move._get_effective_container_locations():
                directions = []
                if dest_location.usage == "internal":
                    directions.append(("inward", dest_location, quantity))
                if source_location.usage == "internal":
                    directions.append(("outward", source_location, quantity))

                for direction, internal_location, direction_qty in directions:
                    if location_id and internal_location.id != location_id:
                        continue
                    yield {
                        "move": move,
                        "direction": direction,
                        "partner_id": move_partner.id or False,
                        "product_id": move.product_id.id,
                        "container_type_id": move.container_type_id.id,
                        "location_id": internal_location.id,
                        "quantity": direction_qty,
                    }

    @api.model
    def get_container_ledger_snapshot(
        self,
        date_from,
        date_to,
        partner_id=False,
        location_id=False,
        container_type_id=False,
    ):
        snapshot = {}
        for impact in self._iter_container_impacts(
            partner_id=partner_id,
            location_id=location_id,
            container_type_id=container_type_id,
        ):
            move_date = fields.Date.to_date(impact["move"].date)
            key = (
                impact["partner_id"],
                impact["container_type_id"],
                impact["location_id"],
            )
            bucket = snapshot.setdefault(
                key,
                {"opening": 0, "inward": 0, "outward": 0, "balance": 0},
            )
            if move_date < date_from:
                if impact["direction"] == "inward":
                    bucket["opening"] += impact["quantity"]
                else:
                    bucket["opening"] -= impact["quantity"]
                continue
            if move_date > date_to:
                continue
            if impact["direction"] == "inward":
                bucket["inward"] += impact["quantity"]
            else:
                bucket["outward"] += impact["quantity"]

        for values in snapshot.values():
            values["balance"] = (
                values["opening"] + values["inward"] - values["outward"]
            )
        return snapshot

    @api.model
    def get_container_balance_snapshot(
        self,
        as_of_date,
        partner_id=False,
        location_ids=False,
        container_type_id=False,
    ):
        snapshot = {}
        for impact in self._iter_container_impacts(
            date_to=as_of_date,
            partner_id=partner_id,
            container_type_id=container_type_id,
        ):
            impact_date = fields.Date.to_date(impact["move"].date)
            if impact_date > as_of_date:
                continue
            if location_ids and impact["location_id"] not in location_ids:
                continue
            key = (
                impact["partner_id"],
                impact["container_type_id"],
                impact["location_id"],
            )
            signed_qty = impact["quantity"] if impact["direction"] == "inward" else -impact["quantity"]
            snapshot[key] = snapshot.get(key, 0) + signed_qty
        return snapshot
