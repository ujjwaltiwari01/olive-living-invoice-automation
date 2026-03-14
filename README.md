# 🫒 Olive Invoice Automation
> **The Intelligent Backbone for Enterprise Financial Workflows**

[![System Status](https://img.shields.io/badge/System_Status-Online-brightgreen?style=for-the-badge)](https://github.com/ujjwaltiwari01/olive-living-invoice-automation)
[![Platform](https://img.shields.io/badge/Platform-Streamlit-FF4B4B?style=for-the-badge)](https://streamlit.io)
[![AI Engine](https://img.shields.io/badge/AI_Engine-GPT--4o_|_Document_AI-blue?style=for-the-badge)](https://cloud.google.com/document-ai)

---

## 💎 The Manager's Lens: Why Olive?

> "Olive isn't just a tool; it's a financial engine that converts administrative friction into operational velocity."

### 🚀 Efficiency Comparison: Manual vs. Olive
| Metric | Manual Entry | Olive Automation | Outcome |
| :--- | :--- | :--- | :--- |
| **Speed** | 5-10 mins / invoice | < 45 seconds | **90% Faster** |
| **Accuracy** | 85-90% (Human error) | 99%+ (AI Verification) | **Total Precision** |
| **Cost** | High Labor Intensity | Automated Scalability | **Lower OPEX** |
| **Visibility** | Paper-based / Siloed | Real-time Dashboard | **Global Insight** |

---

## 🛤️ The Journey of an Invoice (Lifecycle)

Witness the transformation of a raw document into a verified financial record.

```mermaid
stateDiagram-v2
    [*] --> Captured: Upload / Photo
    Captured --> Processing: Image Optimization (L4)
    Processing --> Analyzing: Document AI Extraction (L1)
    Analyzing --> Reasoning: GPT-4o Semantic Mapping (L2)
    Reasoning --> Verifying: Self-Healing Math Check (L3)
    Verifying --> Ready: Human Validation (HITL)
    Ready --> ZohoBooks: API Ingestion
    ZohoBooks --> [*]: Archived & Synced
```

---

## 🏛️ System Blueprint (Data Architecture)

How the "Core Brain" interacts with cloud infrastructure and ERP systems.

```mermaid
graph TD
    User([End User]) -- Uploads --> UI[Streamlit Dashboard]
    
    subgraph "The AI Brain"
        UI -- Raw Data --> L1[Doc AI: OCR Engine]
        L1 -- Semi-Struct --> L2[GPT-4o: Reasoning]
        L2 -- Payload --> L3[Self-Healing Loop]
        L3 -- Refined --> L2
    end
    
    subgraph "External Ecosystem"
        L3 -- Verified --> Zoho[Zoho Books API]
        GCP[Google Cloud] -. IAM .-> L1
        OpenAI[OpenAI] -. API .-> L2
    end
    
    style UI fill:#f1f8ff,stroke:#0366d6,stroke-width:2px
    style L3 fill:#fff5b1,stroke:#fbc02d,stroke-width:2px
    style Zoho fill:#e7f3ff,stroke:#0d47a1,stroke-width:2px
```

---

## 🧬 Intelligence Layers: The "L1-L4" Framework

We don't just read text; we understand financial intent.

> [!IMPORTANT]
> **What is Self-Healing?**
> If the AI detects a math error (e.g., Total doesn't match Line Item sums), it triggers a "Re-read" command, sending the document back to the LLM with specific instructions to fix the discrepancy. This mimics a human bookkeeper's second look.

- **🎨 L4: Visual Clarity** – OpenCV-based enhancements make even blurry mobile photos "AI-readable."
- **🔍 L1: Extraction** – Google Cloud's industrial-grade OCR extracts base entities.
- **🧠 L2: Intelligence** – GPT-4o understands which GSTIN belongs to the vendor vs. Olive.
- **🛡️ L3: Reliability** – Custom logic ensures every rupee is accounted for before manual review.

---

## 📱 Features That Power Your Business

- **📸 Instant Capture**: Specifically tuned for mobile browser cameras.
- **📑 Bulk Processing**: Uploading 100+ invoices? The system queues them automatically.
- **🤖 Smart GST Mapping**: Deep understanding of SGST, CGST, IGST, and HSN codes.
- **👩‍💻 HITL Console**: Human-In-The-Loop interface for ultimate control.

---

## 🛠️ Technology Stack

| Component | Technology | Logo |
| :--- | :--- | :--- |
| **Frontend** | Streamlit | 🎈 |
| **Intelligence** | OpenAI GPT-4o | 🤖 |
| **OCR Infrastructure** | Google Document AI | ☁️ |
| **Business Logic** | Python 3.10+ | 🐍 |
| **ERP Target** | Zoho Books | 💼 |

---

## 🚀 Setup & Launch

> [!TIP]
> Use the `.env.template` (if available) to quickly configure your API keys.

1.  **Environment Sync**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Authentication**:
    Drop your Google Cloud `service-account.json` into the root.
3.  **Blast Off**:
    ```bash
    streamlit run main.py
    ```

---

## 📝 Use Case: The "Field Agent" Scenario
Imagine a site manager at an Olive Living property receiving a fresh supply invoice. They whip out their phone, snap a photo, and by the time they've walked back to their desk, the invoice is already verified and waiting in Zoho Books. **That is Olive Automation.**

---
*© 2024 Olive Living. All rights reserved.*
