"""
Unit tests for the Zoho Schema Transformer (Task 4).

Tests cover: field mapping, calculated field stripping, type enforcement,
validation rules, edge cases, and the master pipeline.
"""
import pytest
from utils.zoho_schema_transformer import (
    normalize_invoice_schema,
    map_invoice_fields,
    map_line_items,
    remove_calculated_fields,
    resolve_customer_id,
    validate_invoice_payload,
    build_zoho_payload,
    CALCULATED_FIELDS,
    FIELDS_TO_DROP,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_verified_payload():
    """Mimics the exact shape of a verified_payload from the HITL interface."""
    return {
        "Invoice Number": "OLV-2025-0042",
        "Estimate Number": None,
        "Invoice Date": "2025-03-01",
        "Invoice Status": "draft",
        "Customer Name": "Olive Living Pvt Ltd",
        "GST Treatment": "business_gst",
        "GST Identification Number (GSTIN)": "27AADCO1234F1Z5",
        "Place of Supply": "MH",
        "TCS Tax Name": None,
        "TCS Percentage": None,
        "TCS Amount": None,
        "TDS Name": None,
        "TDS Percentage": None,
        "TDS Amount": None,
        "Payment Terms": "Net 30",
        "Due Date": "2025-03-31",
        "Currency Code": "INR",
        "Exchange Rate": 1.0,
        "total_amount": 11800.0,
        "tax_amount": 1800.0,
        "Notes": "Thank you for your business",
        "Bypass Math": False,
        "line_items": [
            {
                "Item Name": "Room Cleaning Service",
                "SKU": "SRV-001",
                "Item Desc": "Deep cleaning service for suite rooms",
                "Item Type": "service",
                "HSN/SAC": "998512",
                "Quantity": 2.0,
                "Usage unit": "Nos",
                "Item Price": 5000.0,
                "Item Tax Exemption Reason": None,
                "Is Inclusive Tax": False,
                "Item Tax": "GST18",
                "Item Tax Type": "Tax Group",
                "Item Tax %": 18.0,
            }
        ],
    }


@pytest.fixture
def minimal_payload():
    """Bare minimum payload to test defaults."""
    return {
        "Invoice Number": "INV-001",
        "Invoice Date": "2025-01-01",
        "Customer Name": "Test Customer",
        "line_items": [
            {
                "Item Name": "Widget",
                "Item Price": 100.0,
                "Quantity": 1.0,
            }
        ],
    }


# ===================================================================
# Test normalize_invoice_schema
# ===================================================================
class TestNormalize:

    def test_none_defaults(self):
        """None values should get safe defaults."""
        data = normalize_invoice_schema({
            "Invoice Number": None,
            "Currency Code": None,
            "Exchange Rate": None,
            "line_items": [],
        })
        assert data["Invoice Number"] == ""
        assert data["Currency Code"] == "INR"
        assert data["Exchange Rate"] == 1.0

    def test_due_date_fallback(self):
        """Due Date should default to Invoice Date when missing."""
        data = normalize_invoice_schema({
            "Invoice Date": "2025-06-15",
            "Due Date": "",
            "line_items": [],
        })
        assert data["Due Date"] == "2025-06-15"

    def test_service_to_services(self):
        """Item Type 'service' must become 'services' (Zoho plural)."""
        data = normalize_invoice_schema({
            "line_items": [
                {"Item Name": "Test", "Item Type": "service", "Quantity": 1, "Item Price": 10},
            ],
        })
        assert data["line_items"][0]["Item Type"] == "services"

    def test_goods_stays_goods(self):
        """Item Type 'goods' should stay 'goods'."""
        data = normalize_invoice_schema({
            "line_items": [
                {"Item Name": "Test", "Item Type": "goods", "Quantity": 1, "Item Price": 10},
            ],
        })
        assert data["line_items"][0]["Item Type"] == "goods"

    def test_zero_quantity_becomes_one(self):
        """Quantity <= 0 should default to 1.0."""
        data = normalize_invoice_schema({
            "line_items": [
                {"Item Name": "Test", "Item Price": 10, "Quantity": 0},
            ],
        })
        assert data["line_items"][0]["Quantity"] == 1.0

    def test_unnamed_item(self):
        """Missing Item Name should default to 'Unnamed Item'."""
        data = normalize_invoice_schema({
            "line_items": [{"Item Price": 10, "Quantity": 1}],
        })
        assert data["line_items"][0]["Item Name"] == "Unnamed Item"

    def test_invalid_line_item_skipped(self):
        """Non-dict line items should be dropped."""
        data = normalize_invoice_schema({
            "line_items": ["not a dict", None, 42],
        })
        assert len(data["line_items"]) == 0


# ===================================================================
# Test map_invoice_fields
# ===================================================================
class TestMapInvoiceFields:

    def test_basic_mapping(self, sample_verified_payload):
        normalized = normalize_invoice_schema(sample_verified_payload)
        mapped = map_invoice_fields(normalized)

        assert mapped["invoice_number"] == "OLV-2025-0042"
        assert mapped["date"] == "2025-03-01"
        assert mapped["due_date"] == "2025-03-31"
        assert mapped["customer_name"] == "Olive Living Pvt Ltd"
        assert mapped["currency_code"] == "INR"
        assert mapped["exchange_rate"] == 1.0
        assert mapped["notes"] == "Thank you for your business"
        assert mapped["gst_treatment"] == "business_gst"
        assert mapped["gst_no"] == "27AADCO1234F1Z5"
        assert mapped["place_of_supply"] == "MH"

    def test_is_inclusive_tax_promoted(self):
        """is_inclusive_tax should be promoted to invoice level."""
        normalized = normalize_invoice_schema({
            "line_items": [
                {"Item Name": "A", "Item Price": 10, "Quantity": 1, "Is Inclusive Tax": True},
                {"Item Name": "B", "Item Price": 20, "Quantity": 1, "Is Inclusive Tax": False},
            ],
        })
        mapped = map_invoice_fields(normalized)
        assert mapped["is_inclusive_tax"] is True

    def test_is_inclusive_tax_false(self):
        normalized = normalize_invoice_schema({
            "line_items": [
                {"Item Name": "A", "Item Price": 10, "Quantity": 1, "Is Inclusive Tax": False},
            ],
        })
        mapped = map_invoice_fields(normalized)
        assert mapped["is_inclusive_tax"] is False

    def test_payment_terms_parsed(self):
        """'Net 30' should produce payment_terms=30 and payment_terms_label='Net 30'."""
        normalized = normalize_invoice_schema({
            "Payment Terms": "Net 30",
            "line_items": [],
        })
        mapped = map_invoice_fields(normalized)
        assert mapped["payment_terms"] == 30
        assert mapped["payment_terms_label"] == "Net 30"

    def test_payment_terms_due_on_receipt(self):
        """'Due on Receipt' should produce payment_terms=0."""
        normalized = normalize_invoice_schema({
            "Payment Terms": "Due on Receipt",
            "line_items": [],
        })
        mapped = map_invoice_fields(normalized)
        assert mapped["payment_terms"] == 0

    def test_empty_fields_excluded(self):
        """Empty/None top-level fields should NOT appear in mapped output."""
        normalized = normalize_invoice_schema({
            "Invoice Number": "INV-001",
            "Notes": "",
            "Adjustment": None,
            "line_items": [],
        })
        mapped = map_invoice_fields(normalized)
        assert "notes" not in mapped
        assert "adjustment" not in mapped


# ===================================================================
# Test map_line_items
# ===================================================================
class TestMapLineItems:

    def test_basic_line_item(self, sample_verified_payload):
        normalized = normalize_invoice_schema(sample_verified_payload)
        items = map_line_items(normalized["line_items"])

        assert len(items) == 1
        item = items[0]
        assert item["name"] == "Room Cleaning Service"
        assert item["description"] == "Deep cleaning service for suite rooms"
        assert item["rate"] == 5000.0
        assert item["quantity"] == 2.0
        assert item["hsn_or_sac"] == "998512"
        assert item["tax_percentage"] == 18.0
        assert item["tax_name"] == "GST18"
        assert item["tax_type"] == "Tax Group"
        assert item["product_type"] == "services"
        assert item["unit"] == "Nos"

    def test_rate_is_float(self):
        items = map_line_items([{"Item Name": "X", "Item Price": "250", "Quantity": "3"}])
        assert isinstance(items[0]["rate"], float)
        assert isinstance(items[0]["quantity"], float)

    def test_missing_name_defaulted(self):
        items = map_line_items([{"Item Price": 10, "Quantity": 1}])
        assert items[0]["name"] == "Unnamed Item"

    def test_multiple_items(self):
        items = map_line_items([
            {"Item Name": "A", "Item Price": 100, "Quantity": 1},
            {"Item Name": "B", "Item Price": 200, "Quantity": 2},
        ])
        assert len(items) == 2
        assert items[0]["name"] == "A"
        assert items[1]["name"] == "B"
        assert items[1]["rate"] == 200.0


# ===================================================================
# Test remove_calculated_fields
# ===================================================================
class TestRemoveCalculatedFields:

    def test_strips_calculated(self):
        payload = {
            "invoice_number": "INV-001",
            "sub_total": 1000,
            "tax_total": 180,
            "total": 1180,
            "balance": 1180,
            "payment_made": 0,
            "credits_applied": 0,
            "line_items": [],
        }
        cleaned = remove_calculated_fields(payload)
        for field in CALCULATED_FIELDS:
            assert field not in cleaned
        assert cleaned["invoice_number"] == "INV-001"
        assert cleaned["line_items"] == []

    def test_strips_drop_fields(self):
        payload = {
            "invoice_number": "INV-001",
            "Bypass Math": True,
            "TCS Amount": 24.0,
            "Invoice Status": "draft",
        }
        cleaned = remove_calculated_fields(payload)
        assert "Bypass Math" not in cleaned
        assert "TCS Amount" not in cleaned
        assert "Invoice Status" not in cleaned


# ===================================================================
# Test resolve_customer_id
# ===================================================================
class TestResolveCustomerId:

    def test_returns_customer_name(self):
        result = resolve_customer_id("Olive Living Pvt Ltd")
        assert result["customer_name"] == "Olive Living Pvt Ltd"
        assert result["_requires_customer_id_resolution"] is True

    def test_empty_name(self):
        result = resolve_customer_id("")
        assert result["customer_name"] == "Unknown Customer"

    def test_none_name(self):
        result = resolve_customer_id(None)
        assert result["customer_name"] == "Unknown Customer"


# ===================================================================
# Test validate_invoice_payload
# ===================================================================
class TestValidatePayload:

    def test_valid_payload(self):
        payload = {
            "customer_name": "Test",
            "date": "2025-03-01",
            "currency_code": "INR",
            "gst_treatment": "business_gst",
            "exchange_rate": 1.0,
            "gst_no": "27AADCO1234F1Z5",
            "line_items": [
                {"name": "Item", "rate": 100.0, "quantity": 1.0},
            ],
        }
        is_valid, errors = validate_invoice_payload(payload)
        assert is_valid is True
        assert errors == []

    def test_missing_customer(self):
        payload = {"line_items": [{"name": "X", "rate": 10, "quantity": 1}]}
        is_valid, errors = validate_invoice_payload(payload)
        assert is_valid is False
        assert any("customer_id" in e for e in errors)

    def test_empty_line_items(self):
        payload = {"customer_name": "Test", "line_items": []}
        is_valid, errors = validate_invoice_payload(payload)
        assert is_valid is False
        assert any("at least one line item" in e for e in errors)

    def test_missing_rate(self):
        payload = {
            "customer_name": "Test",
            "line_items": [{"name": "X", "quantity": 1}],
        }
        is_valid, errors = validate_invoice_payload(payload)
        assert is_valid is False
        assert any("rate" in e for e in errors)

    def test_missing_quantity(self):
        payload = {
            "customer_name": "Test",
            "line_items": [{"name": "X", "rate": 10}],
        }
        is_valid, errors = validate_invoice_payload(payload)
        assert is_valid is False
        assert any("quantity" in e for e in errors)

    def test_zero_quantity(self):
        payload = {
            "customer_name": "Test",
            "line_items": [{"name": "X", "rate": 10, "quantity": 0}],
        }
        is_valid, errors = validate_invoice_payload(payload)
        assert is_valid is False
        assert any("quantity" in e and "> 0" in e for e in errors)

    def test_invalid_date_format(self):
        payload = {
            "customer_name": "Test",
            "date": "01/03/2025",
            "line_items": [{"name": "X", "rate": 10, "quantity": 1}],
        }
        is_valid, errors = validate_invoice_payload(payload)
        assert is_valid is False
        assert any("yyyy-mm-dd" in e for e in errors)

    def test_invalid_currency(self):
        payload = {
            "customer_name": "Test",
            "currency_code": "INRR",
            "line_items": [{"name": "X", "rate": 10, "quantity": 1}],
        }
        is_valid, errors = validate_invoice_payload(payload)
        assert is_valid is False
        assert any("3-letter" in e for e in errors)

    def test_invalid_gst_treatment(self):
        payload = {
            "customer_name": "Test",
            "gst_treatment": "invalid_value",
            "line_items": [{"name": "X", "rate": 10, "quantity": 1}],
        }
        is_valid, errors = validate_invoice_payload(payload)
        assert is_valid is False
        assert any("gst_treatment" in e for e in errors)

    def test_invalid_gst_no_length(self):
        payload = {
            "customer_name": "Test",
            "gst_no": "12345",
            "line_items": [{"name": "X", "rate": 10, "quantity": 1}],
        }
        is_valid, errors = validate_invoice_payload(payload)
        assert is_valid is False
        assert any("15 characters" in e for e in errors)

    def test_negative_exchange_rate(self):
        payload = {
            "customer_name": "Test",
            "exchange_rate": -1.0,
            "line_items": [{"name": "X", "rate": 10, "quantity": 1}],
        }
        is_valid, errors = validate_invoice_payload(payload)
        assert is_valid is False
        assert any("exchange_rate" in e for e in errors)


# ===================================================================
# Test build_zoho_payload (integration / master pipeline)
# ===================================================================
class TestBuildZohoPayload:

    def test_full_pipeline(self, sample_verified_payload):
        payload, is_valid, errors = build_zoho_payload(sample_verified_payload)

        assert is_valid is True
        assert errors == []

        # Top-level mappings
        assert payload["invoice_number"] == "OLV-2025-0042"
        assert payload["date"] == "2025-03-01"
        assert payload["due_date"] == "2025-03-31"
        assert payload["customer_name"] == "Olive Living Pvt Ltd"
        assert payload["currency_code"] == "INR"
        assert payload["gst_treatment"] == "business_gst"
        assert payload["gst_no"] == "27AADCO1234F1Z5"
        assert payload["place_of_supply"] == "MH"
        assert payload["notes"] == "Thank you for your business"
        assert payload["is_inclusive_tax"] is False
        assert payload["payment_terms"] == 30
        assert payload["payment_terms_label"] == "Net 30"

        # Customer ID stub
        assert payload["_requires_customer_id_resolution"] is True

        # Calculated fields absent
        assert "total_amount" not in payload
        assert "tax_amount" not in payload
        assert "sub_total" not in payload
        assert "total" not in payload

        # Dropped fields absent
        assert "Estimate Number" not in payload
        assert "Invoice Status" not in payload
        assert "TCS Amount" not in payload
        assert "Bypass Math" not in payload
        assert "SKU" not in payload

        # Line items
        assert len(payload["line_items"]) == 1
        item = payload["line_items"][0]
        assert item["name"] == "Room Cleaning Service"
        assert item["rate"] == 5000.0
        assert item["quantity"] == 2.0
        assert item["hsn_or_sac"] == "998512"
        assert item["product_type"] == "services"

    def test_minimal_payload(self, minimal_payload):
        payload, is_valid, errors = build_zoho_payload(minimal_payload)
        assert is_valid is True
        assert payload["invoice_number"] == "INV-001"
        assert payload["date"] == "2025-01-01"
        assert len(payload["line_items"]) == 1

    def test_empty_invoice_rejected(self):
        payload, is_valid, errors = build_zoho_payload({})
        assert is_valid is False
        assert any("line item" in e for e in errors)

    def test_no_calculated_fields_in_output(self, sample_verified_payload):
        """Ensure no calculated field leaks into the final output."""
        sample_verified_payload["sub_total"] = 10000.0
        sample_verified_payload["total"] = 11800.0
        sample_verified_payload["balance"] = 11800.0
        payload, _, _ = build_zoho_payload(sample_verified_payload)
        for field in CALCULATED_FIELDS:
            assert field not in payload, f"Calculated field '{field}' leaked into output"
