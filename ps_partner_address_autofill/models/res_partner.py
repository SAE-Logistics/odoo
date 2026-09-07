from odoo import models, api


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def get_google_places_api_key(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "ps_partner_address_autofill.google_api_key"
        ) or False

    @api.model
    def _find_country_state(self, country, candidates):
        """Match a Google admin area against ``res.country.state``.

        ``candidates`` is a list of ``(code, name)`` pairs, most specific
        first. Name is tried before code: Google's ``short_name`` for an admin
        area is an informal abbreviation, not the ISO subdivision code Odoo
        stores, so a code hit is the weaker signal. Returns an empty recordset
        when nothing matches.
        """
        State = self.env["res.country.state"].sudo()
        for code, name in candidates:
            for field, term in (("name", name), ("code", code)):
                # `=ilike ''` matches nothing, but skip anyway: an empty term
                # means Google did not supply that part.
                if not term:
                    continue
                state = State.search(
                    [("country_id", "=", country.id), (field, "=ilike", term)],
                    limit=1,
                )
                if state:
                    return state
        return State

    @api.model
    def parse_google_place_details(self, place):
        """Turn a Google Place payload into Odoo address values.

        ``country_id`` and ``state_id`` come back as ``{"id", "display_name"}``
        dicts, or ``False`` when nothing matched; the web client reshapes them
        to whatever its ``record.update()`` expects.
        """
        components = place.get("address_components", [])
        formatted = place.get("formatted_address") or ""

        def get(types, key="long_name"):
            """First component matching any of `types`, in the given order."""
            if isinstance(types, str):
                types = [types]
            for wanted in types:
                for component in components:
                    if wanted in component.get("types", []):
                        return component.get(key) or ""
            return ""

        # Street line: number + route, never the whole formatted address
        # (city/zip/country get their own fields).
        street = " ".join(
            part for part in (get("street_number"), get("route")) if part
        )
        if not street:
            street = get(["premise", "establishment", "point_of_interest"]) or (
                formatted.split(",")[0].strip()
            )

        street2 = get(["subpremise", "neighborhood"])

        # `postal_town` first: UK towns are returned there, not as `locality`.
        city = get([
            "postal_town",
            "locality",
            "sublocality_level_1",
            "sublocality",
            "administrative_area_level_2",
        ])

        country_code = get("country", "short_name")
        country_name = get("country")

        Country = self.env["res.country"].sudo()
        country = Country
        if country_code:
            country = Country.search([("code", "=ilike", country_code)], limit=1)
        if not country and country_name:
            country = Country.search([("name", "=ilike", country_name)], limit=1)

        state = self.env["res.country.state"]
        if country:
            # Most specific first. Google puts the useful "county" in
            # level 1 for countries like India ("Maharashtra") but in level 2
            # for the UK ("Hertfordshire", where level 1 is just "England").
            candidates = [
                (
                    get("administrative_area_level_2", "short_name"),
                    get("administrative_area_level_2"),
                ),
                (
                    get("administrative_area_level_1", "short_name"),
                    get("administrative_area_level_1"),
                ),
            ]
            state = self._find_country_state(country, candidates)

        return {
            "street": street,
            "street2": street2,
            "city": city,
            "zip": get("postal_code"),
            "country_id": (
                {"id": country.id, "display_name": country.display_name}
                if country
                else False
            ),
            "state_id": (
                {"id": state.id, "display_name": state.display_name}
                if state
                else False
            ),
        }
