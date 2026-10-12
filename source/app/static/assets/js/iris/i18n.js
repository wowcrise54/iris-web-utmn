/*
 * IRIS client-side i18n runtime.
 *
 * The server injects the active catalog as `window.IRIS_I18N` (see
 * templates/includes/i18n_scripts.html). UI code calls the explicit helpers:
 *
 *     t("Dashboard")                       -> translated string
 *     t("Hello {name}", {name: user})      -> placeholder substitution
 *     ngettext("task", "tasks", n)         -> plural form, then substitution
 *
 * Nothing here walks or rewrites the DOM: only strings that developers pass to
 * t()/ngettext() are translated, so user data and enum values stay untouched.
 */
(function (window) {
    "use strict";

    var catalog = window.IRIS_I18N || {locale: "en", fallback: "en", messages: {}, plurals: {}};
    catalog.messages = catalog.messages || {};
    catalog.plurals = catalog.plurals || {};

    function substitute(text, params) {
        if (!params) {
            return text;
        }
        return text.replace(/\{(\w+)\}/g, function (match, key) {
            return Object.prototype.hasOwnProperty.call(params, key) ? String(params[key]) : match;
        });
    }

    // CLDR plural index for the active locale. Keep in sync with
    // app/i18n.py::_plural_index.
    function pluralIndex(count) {
        var n = Math.abs(parseInt(count, 10) || 0);
        if (catalog.locale === "ru") {
            if (n % 10 === 1 && n % 100 !== 11) {
                return 0;
            }
            if (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14)) {
                return 1;
            }
            return 2;
        }
        return n === 1 ? 0 : 1;
    }

    function t(msgid, params) {
        var text = catalog.messages[msgid] || msgid;
        return substitute(text, params);
    }

    function ngettext(singular, plural, count, params) {
        var forms = catalog.plurals[singular];
        var text;
        if (forms && forms.length) {
            var index = pluralIndex(count);
            text = forms[index] || forms[0];
        } else {
            text = pluralIndex(count) === 0 ? singular : plural;
        }
        return substitute(text, params);
    }

    catalog.t = t;
    catalog.ngettext = ngettext;
    catalog.substitute = substitute;
    catalog.pluralIndex = pluralIndex;

    window.IRIS_I18N = catalog;
    window.t = t;
    window.ngettext = ngettext;

    // The shared layouts load these plugins before the catalog. Configure their
    // UI defaults before any page creates a table or a picker. Data stays intact.
    if (catalog.locale === "ru" && window.jQuery) {
        var $ = window.jQuery;
        if ($.fn.dataTable) {
            $.extend(true, $.fn.dataTable.defaults, {
                language: {
                    emptyTable: t("No data available in table"),
                    info: t("Showing _START_ to _END_ of _TOTAL_ entries"),
                    infoEmpty: t("Showing 0 to 0 of 0 entries"),
                    infoFiltered: t("(filtered from _MAX_ total entries)"),
                    lengthMenu: t("Show _MENU_ entries"),
                    loadingRecords: t("Loading..."),
                    processing: t("Processing..."),
                    search: t("Search:"),
                    zeroRecords: t("No matching records found"),
                    paginate: {first: t("First"), last: t("Last"), next: t("Next"), previous: t("Previous")},
                    aria: {
                        sortAscending: ": " + t("Activate to sort column ascending"),
                        sortDescending: ": " + t("Activate to sort column descending")
                    },
                    buttons: {copy: t("Copy"), colvis: t("Columns"), copyTitle: t("Copied"),
                        copySuccess: {1: t("Copied one row"), _: t("Copied %d rows")}}
                }
            });
        }
        if ($.fn.selectpicker) {
            $.fn.selectpicker.defaults = $.extend({}, $.fn.selectpicker.defaults, {
                noneSelectedText: t("Nothing selected"),
                noneResultsText: t("No results matched {0}"),
                countSelectedText: t("Selected {0} of {1}"),
                selectAllText: t("Select all"),
                deselectAllText: t("Deselect All"),
                doneButtonText: t("Close")
            });
        }
    }
})(window);
