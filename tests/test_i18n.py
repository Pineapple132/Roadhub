import re
from roadhub import i18n, i18n_data


def test_catalog_placeholders_consistent():
    for key, vals in i18n_data.CATALOG.items():
        n = key.count("{}")
        for v in vals:
            assert len(re.findall(r"\{\d*\}", v)) == n, key


def test_tr_plain_and_template():
    i18n.set_language("en")
    try:
        assert i18n.tr("Fahrer {}".format("X")) == "Driver X"
        assert i18n.source(i18n.tr("Fahrer {}".format("X"))) in ("Fahrer X", "Driver X")
        assert i18n.tr("gibt-es-nicht-xyz") == "gibt-es-nicht-xyz"
    finally:
        i18n.set_language("de")
