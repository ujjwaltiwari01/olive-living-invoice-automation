from pydantic import BaseModel, Field
from typing import List, Optional

class ZohoLineItem(BaseModel):
    item_name: str = Field(alias="Item Name", description="Short name of the product or service. e.g., 'Room Charge', 'Paracetamol 500mg'")
    sku: Optional[str] = Field(default="", alias="SKU", description="Stock Keeping Unit or internal code if available.")
    item_desc: Optional[str] = Field(default="", alias="Item Desc", description="Detailed description of the line item.")
    item_type: str = Field(alias="Item Type", description="Must be exactly 'goods' or 'service'. Hospital rooms, doctor consults, and hotel stays are 'service'. Medicines, food, physical items are 'goods'.")
    hsn_sac: Optional[str] = Field(default="", alias="HSN/SAC", description="HSN (for goods) or SAC (for services) code if mentioned.")
    quantity: float = Field(alias="Quantity", description="Quantity of the item. Default to 1 if not specified.")
    usage_unit: Optional[str] = Field(default="count", alias="Usage unit", description="Unit of measurement e.g., 'count', 'hrs', 'kgs', 'nights'. default is 'count'.")
    item_price: float = Field(alias="Item Price", description="Unit price of the item before tax.")
    item_tax_exemption_reason: Optional[str] = Field(default="", alias="Item Tax Exemption Reason", description="Reason for exemption if tax is 0%.")
    is_inclusive_tax: bool = Field(default=False, alias="Is Inclusive Tax", description="True if the item price already includes tax.")
    
    # Tax fields mapping to Indian GST
    item_tax: Optional[str] = Field(default="", alias="Item Tax", description="Tax group name e.g., 'IGST18', 'GST18', 'GST5'. Leave empty if no tax.")
    item_tax_type: Optional[str] = Field(default="", alias="Item Tax Type", description="Either 'Tax Group' or 'ItemAmount'. Usually 'Tax Group' for standard GST.")
    item_tax_percentage: float = Field(default=0.0, alias="Item Tax %", description="The percentage of tax applied to this item.")

class ZohoInvoiceSchema(BaseModel):
    invoice_number: str = Field(alias="Invoice Number", description="Unique invoice identifier.")
    estimate_number: Optional[str] = Field(default="", alias="Estimate Number")
    invoice_date: str = Field(alias="Invoice Date", description="Date of the invoice in YYYY-MM-DD format.")
    invoice_status: str = Field(default="Draft", alias="Invoice Status", description="Set to 'Draft' by default.")
    customer_name: str = Field(alias="Customer Name", description="Name of the customer or patient.")
    
    # Complex Indian Tax Rules
    gst_treatment: str = Field(
        alias="GST Treatment", 
        description="Must be one of: 'business_gst', 'business_none', 'consumer', 'overseas', 'business_sez'. 'consumer' for B2C hospital/hotel bills. 'business_gst' for B2B if GSTIN is present."
    )
    gstin: Optional[str] = Field(default="", alias="GST Identification Number (GSTIN)", description="Customer's GSTIN if available.")
    place_of_supply: Optional[str] = Field(default="", alias="Place of Supply", description="Two letter state code (e.g., 'MH', 'KA', 'DL') where supply is made. Required if GST is applied.")
    
    # TDS / TCS
    tcs_tax_name: Optional[str] = Field(default="", alias="TCS Tax Name")
    tcs_percentage: Optional[float] = Field(default=0.0, alias="TCS Percentage")
    tcs_amount: Optional[float] = Field(default=0.0, alias="TCS Amount")
    tds_name: Optional[str] = Field(default="", alias="TDS Name")
    tds_percentage: Optional[float] = Field(default=0.0, alias="TDS Percentage")
    tds_amount: Optional[float] = Field(default=0.0, alias="TDS Amount")
    
    # Terms
    payment_terms: Optional[str] = Field(default="Due on Receipt", alias="Payment Terms", description="Default is 'Due on Receipt'")
    due_date: Optional[str] = Field(default="", alias="Due Date", description="Due date in YYYY-MM-DD. If not provided, same as Invoice Date.")
    
    # Base configuration
    currency_code: str = Field(default="INR", alias="Currency Code", description="3-letter currency code (INR, USD).")
    exchange_rate: float = Field(default=1.0, alias="Exchange Rate")
    
    # Line Items
    line_items: List[ZohoLineItem] = Field(description="List of items/services on the invoice.")
    
    # Final Totals (for validation, not mapped directly in the CSV layout but needed for consistency)
    total_amount: float = Field(description="The final total amount on the invoice. Used for validation, not in CSV.")
    tax_amount: float = Field(description="Total tax amount. Used for validation, not in CSV.")
    notes: Optional[str] = Field(default="", alias="Notes", description="Any notes or terms on the invoice.")
