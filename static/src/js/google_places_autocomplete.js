/** @odoo-module **/

import { registry } from "@web/core/registry";
import {
    Component,
    onMounted,
    onPatched,
    onWillDestroy,
    onWillStart,
    useRef,
    useState,
} from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const GMAPS_CALLBACK = "__psGooglePlacesLoaded";
const PLACE_FIELDS = ["addressComponents", "formattedAddress"];
const MIN_QUERY_LENGTH = 3;
const DEBOUNCE_MS = 300;
const M2O_FIELDS = ["country_id", "state_id"];

let placesAPILoadPromise = null;

// Odoo 17 stores a many2one as `[id, display_name]`, Odoo 18 as
// `{ id, display_name }`. Writing the wrong one leaves the field empty
// *without raising*, so the shape is learned from a write that sticks and
// cached for the rest of the session.
let many2oneShape = "object";

function buildMany2one(data, shape) {
    if (!data) {
        return false;
    }
    return shape === "array"
        ? [data.id, data.display_name]
        : { id: data.id, display_name: data.display_name };
}

function shapeMany2oneValues(values, fieldNames, shape) {
    return Object.fromEntries(
        fieldNames.map((name) => [name, buildMany2one(values[name], shape)])
    );
}

/**
 * Load the Google Maps JS API (places library) once per page.
 * Resolves to true when the Places autocomplete service is usable.
 */
function loadPlacesAPI(orm) {
    if (window.google?.maps?.places?.AutocompleteSuggestion) {
        return Promise.resolve(true);
    }
    if (!placesAPILoadPromise) {
        placesAPILoadPromise = (async () => {
            const apiKey = await orm.call("res.partner", "get_google_places_api_key", []);
            if (!apiKey) {
                return false;
            }
            const loaded = await new Promise((resolve) => {
                window[GMAPS_CALLBACK] = () => resolve(true);
                const script = document.createElement("script");
                script.async = true;
                script.src =
                    "https://maps.googleapis.com/maps/api/js" +
                    `?key=${encodeURIComponent(apiKey)}` +
                    `&libraries=places&loading=async&callback=${GMAPS_CALLBACK}`;
                script.onerror = () => {
                    placesAPILoadPromise = null;
                    resolve(false);
                };
                document.head.appendChild(script);
            });
            return loaded && !!window.google?.maps?.places?.AutocompleteSuggestion;
        })().catch(() => {
            placesAPILoadPromise = null;
            return false;
        });
    }
    return placesAPILoadPromise;
}

/**
 * Char field rendered as a plain Odoo input, with a Google Places suggestion
 * dropdown. Selecting a suggestion fills street/street2/city/zip/state/country.
 * Without an API key (or if Google fails to load) it degrades to a normal
 * editable char field.
 */
export class GooglePlacesAutocompleteField extends Component {
    static template = "ps_partner_address_autofill.GooglePlacesAutocompleteField";
    static props = {
        ...standardFieldProps,
        placeholder: { type: String, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.inputRef = useRef("input");

        this.state = useState({
            apiLoaded: false,
            // Display data only. The Google prediction objects are kept out of
            // the reactive store: proxying them breaks their internal state.
            suggestions: [],
            activeIndex: -1,
            open: false,
        });

        this.predictions = [];
        this.sessionToken = null;
        this.debounceHandle = null;
        this.querySeq = 0;

        onWillStart(async () => {
            this.state.apiLoaded = await loadPlacesAPI(this.orm);
        });
        onMounted(() => this.syncInput());
        onPatched(() => this.syncInput());
        onWillDestroy(() => clearTimeout(this.debounceHandle));
    }

    get value() {
        return this.props.record.data[this.props.name] || "";
    }

    /** Push the record value into the DOM input, unless the user is typing. */
    syncInput() {
        const el = this.inputRef.el;
        if (el && document.activeElement !== el && el.value !== this.value) {
            el.value = this.value;
        }
    }

    closeDropdown() {
        this.state.open = false;
        this.state.activeIndex = -1;
    }

    // -- input handling ----------------------------------------------------

    onInput(ev) {
        const query = ev.target.value;
        clearTimeout(this.debounceHandle);
        if (!this.state.apiLoaded || query.trim().length < MIN_QUERY_LENGTH) {
            this.closeDropdown();
            return;
        }
        this.debounceHandle = setTimeout(() => this.fetchSuggestions(query), DEBOUNCE_MS);
    }

    /** Typed-in text is saved like any other char field. */
    onChange(ev) {
        this.props.record.update({ [this.props.name]: ev.target.value });
    }

    onBlur() {
        this.closeDropdown();
    }

    onKeydown(ev) {
        if (!this.state.open || !this.state.suggestions.length) {
            return;
        }
        const count = this.state.suggestions.length;
        switch (ev.key) {
            case "ArrowDown":
                ev.preventDefault();
                this.state.activeIndex = (this.state.activeIndex + 1) % count;
                break;
            case "ArrowUp":
                ev.preventDefault();
                this.state.activeIndex = (this.state.activeIndex - 1 + count) % count;
                break;
            case "Enter":
                if (this.state.activeIndex >= 0) {
                    ev.preventDefault();
                    ev.stopPropagation();
                    this.selectSuggestion(this.state.activeIndex);
                }
                break;
            case "Escape":
                ev.stopPropagation();
                this.closeDropdown();
                break;
        }
    }

    // -- Google Places -----------------------------------------------------

    async fetchSuggestions(query) {
        const seq = ++this.querySeq;
        const places = window.google?.maps?.places;
        if (!places?.AutocompleteSuggestion) {
            return;
        }
        try {
            // One session token spans the keystrokes of a single lookup and is
            // discarded once place details are fetched (Google billing rule).
            if (!this.sessionToken) {
                this.sessionToken = new places.AutocompleteSessionToken();
            }
            const { suggestions } = await places.AutocompleteSuggestion.fetchAutocompleteSuggestions(
                { input: query, sessionToken: this.sessionToken }
            );
            if (seq !== this.querySeq) {
                return; // a later keystroke already won
            }
            this.predictions = suggestions.map((s) => s.placePrediction).filter(Boolean);
            this.state.suggestions = this.predictions.map((p) => ({
                mainText: String(p.mainText || p.text || ""),
                secondaryText: String(p.secondaryText || ""),
            }));
            this.state.activeIndex = -1;
            this.state.open = this.state.suggestions.length > 0;
        } catch (error) {
            console.error("Google Places suggestions failed", error);
            this.closeDropdown();
        }
    }

    async selectSuggestion(index) {
        const prediction = this.predictions[index];
        if (!prediction) {
            return;
        }
        this.closeDropdown();
        try {
            const place = prediction.toPlace();
            await place.fetchFields({ fields: PLACE_FIELDS });
            await this.applyPlace(place);
        } catch (error) {
            console.error(
                "Google Places autofill failed",
                error?.data?.message || error,
                error?.data?.debug || ""
            );
            this.notification.add(_t("Could not fill in the selected address."), {
                type: "danger",
            });
        } finally {
            this.sessionToken = null;
        }
    }

    async applyPlace(place) {
        const legacyPlace = {
            formatted_address: place.formattedAddress,
            address_components: (place.addressComponents || []).map((c) => ({
                long_name: c.longText,
                short_name: c.shortText,
                types: c.types,
            })),
        };
        const values = await this.orm.call("res.partner", "parse_google_place_details", [
            legacyPlace,
        ]);
        await this.writeValues(values);
        // The input still holds the typed query; replace it with what we stored.
        if (this.inputRef.el) {
            this.inputRef.el.value = values[this.props.name] || "";
        }
    }

    /**
     * Write the parsed address, retrying the many2one fields with the other
     * value shape if the first attempt did not take.
     */
    async writeValues(values) {
        const record = this.props.record;
        const shape = many2oneShape;
        const other = shape === "object" ? "array" : "object";

        try {
            await record.update({
                ...values,
                ...shapeMany2oneValues(values, M2O_FIELDS, shape),
            });
        } catch (error) {
            console.warn(`Rejected as ${shape} many2one, retrying`, error);
        }

        const missed = M2O_FIELDS.filter((name) => values[name] && !record.data[name]);
        if (!missed.length) {
            return;
        }
        await record.update(shapeMany2oneValues(values, missed, other));
        if (missed.every((name) => record.data[name])) {
            many2oneShape = other;
        } else {
            console.warn(
                "Could not set",
                missed.join(", "),
                "- neither many2one shape was accepted",
                missed.map((name) => values[name])
            );
        }
    }
}

registry.category("fields").add("google_places_autocomplete", {
    component: GooglePlacesAutocompleteField,
    supportedTypes: ["char"],
    extractProps: ({ attrs }) => ({ placeholder: attrs.placeholder }),
});
