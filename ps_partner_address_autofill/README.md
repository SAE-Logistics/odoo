# Partner Address Autofill with Google Places

Google Places autocomplete on the Odoo partner address. Type into the **Street**
field, pick a suggestion, and Street / Street2 / City / Zip / County-State /
Country are filled in together.

Odoo 18. Module version `18.0.1.2.0`.

---

## Credits and license

This is a **modified fork**. The original module was written by
**PySquad Informatics LLP** (<https://pysquad.com/>) and published on the Odoo
Apps store:

<https://apps.odoo.com/apps/modules/18.0/ps_partner_address_autofill>

The fork is maintained by **Pradeep Maheepala (eartisan)** and is distributed
under the **LGPL-3**, the same licence as the original. See [LICENSE](LICENSE)
(and [COPYING.GPL](COPYING.GPL), which LGPL-3 incorporates by reference).

The technical module name is unchanged (`ps_partner_address_autofill`), so this
fork **replaces** the upstream module rather than installing alongside it. Do
not publish it to the Odoo Apps store under that name.

---

## Changes from the upstream release

**Google Places API**

- Rewritten against `google.maps.places.AutocompleteSuggestion`, replacing the
  deprecated `Autocomplete` service.
- Suggestions render in a custom OWL dropdown instead of Google's injected
  widget, so the field keeps standard Odoo input styling and works inside
  dialogs.
- One `AutocompleteSessionToken` per lookup, discarded after place details are
  fetched, per Google's billing rules.
- 300 ms debounce and a 3-character minimum before any request is made.
- Keyboard navigation (arrows / Enter / Escape) over the suggestion list.

**Bug fixes**

- Input no longer truncates mid-typing. The record value was bound reactively to
  the DOM `value` property, so every OWL patch overwrote in-progress typing and
  the field reverted to the closest earlier match. The value is now pushed in
  only when the input is not focused.
- The first line of the address now saves correctly.
- **County / State** now resolves for UK addresses. The original only looked at
  `administrative_area_level_1`, which Google fills with "England" for UK
  places; the county lives in `administrative_area_level_2`. Matching now tries
  level 2 first, then level 1.
- State matching prefers **name over code**. Google's `short_name` for an admin
  area is an informal abbreviation, not the ISO 3166-2 code Odoo stores, so a
  code hit is the weaker signal and could otherwise override a correct name
  match.
- Many2one writes work on both Odoo 17 (`[id, display_name]`) and Odoo 18
  (`{id, display_name}`). The wrong shape leaves the field empty *without
  raising*, so the widget writes, checks whether the value stuck, retries with
  the other shape, and caches the answer for the session.

**Features**

- Autocomplete also works in the **Create Contact** dialog under a company's
  *Contacts & Addresses* tab, not just the top-level partner form.
- Graceful degradation: with no API key, or if the Google script fails to load,
  the field behaves as a plain editable char field.

---

## Installation

The repository is named `ps-partner-address-autocomplete`, but Odoo requires the
addon directory to match the technical module name. Clone into the right name:

```bash
git clone https://github.com/eartisan-uk/ps-partner-address-autocomplete.git \
    ps_partner_address_autofill
```

Then update the apps list and install **Partner Address Autofill with Google
Places**.

## Configuration

1. Create a Google Cloud project and enable the **Places API (New)**.
2. Create an API key. Restrict it by HTTP referrer to your Odoo domain.
3. In Odoo: **Settings → Technical → Parameters → System Parameters**.
4. Add a parameter:

   | Key | Value |
   | --- | --- |
   | `ps_partner_address_autofill.google_api_key` | *your API key* |

The key is read server-side and passed to the browser only to load the Maps JS
SDK, which is how Google's client-side Places API is designed to work — restrict
the key by referrer.

## Usage

Open any contact and start typing in the **Street** field (at least three
characters). Pick a suggestion; the rest of the address block fills in. The same
box appears in the *Create Contact* dialog under *Contacts & Addresses*.

Country and county/state are matched against existing `res.country` and
`res.country.state` records. Nothing is auto-created — if a region is missing
from your database, that field is left empty.
