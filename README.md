# 🛒 CARE: AI-Powered Intelligent Customer Experience Platform

## Redefining post-purchase customer support with autonomous resolution, multimodal interaction, and proactive subscription management.

This project transforms traditional post-purchase customer support into a proactive, intelligent, and deeply personalized service. The CARE (Customer Assistance Resolution Engine) leverages advanced conversational AI and a multi-faceted architecture to address customer needs in real-time, moving beyond mere information retrieval to validated problem resolution and integrated service delivery, all while maintaining robust human oversight.

---

## 💡 Core Architecture & Features

### 🧠 Conversational AI & Natural Language Understanding (NLU)

At its heart, the system utilizes a powerful Large Language Model (LLM) (powered by Groq) to understand natural language queries, interpret user intent (e.g., `ORDER_STATUS`, `REFUND_REQUEST`, `DELIVERY_ISSUE`), and generate human-like responses. This forms the foundation for all customer interactions.

### ⚙ Autonomous Resolution Engine with Intelligent Validation & Human-in-the-Loop

A key differentiator, this engine enables the AI to not just respond but to act on the backend to resolve common issues autonomously.

*   **Automated Fixes:** For straightforward problems (e.g., wallet mismatch or missing payments), the AI simulates backend fixes like re-syncing or confirming payments and informs the user accordingly.
*   **Evidence-Based Validation:** For sensitive issues (e.g., refunds), the AI prompts users to submit visual evidence (e.g., an image of a damaged product). It analyzes both the image and textual complaint to assess validity using the **Gemini API**.
    *   ✅ **If valid:** Refund is processed autonomously.
    *   ❓ **If uncertain:** Case escalated to human agents via a Human-in-the-Loop (HITL) system for manual review.
This ensures both efficiency and reliability without compromising on quality or customer trust.

### 📦 Subscription Model & Proactive Management

To boost customer convenience and retention, the system includes a fully integrated subscription model, developed to automate recurring deliveries and provide timely reminders.

#### 🔁 Key Features:
*   **Recurring Order Automation**: Customers can subscribe to recurring deliveries for selected items (e.g., weekly). Delivery dates are automatically calculated and updated. All subscription data is persisted in **MongoDB Atlas**.
*   **Simple UI & Backend Integration**: Users create subscriptions via a form in the "Autonomous Order Planner" page of the Streamlit UI. The system generates a unique subscription ID (e.g., `SUB002`) and saves it through the FastAPI using the `SubscriptionManager` class.
*   **Subscription Management Tools**: Users can view active subscriptions with details like: Items, quantity, delivery day, next delivery, and status. Subscriptions can be cancelled easily through the UI.
*   **Notification System**: Customers are alerted 1–2 days before delivery. For example: "Reminder: Your subscription SUB001 will restock Amul Milk 1L on 2025-07-18." These are shown under "Upcoming Deliveries" using a dedicated API endpoint.

#### 🔧 Technical Implementation:
*   **Data Layer**: All data is stored in **MongoDB Atlas** for persistence and scalability.
*   **Endpoints** (via FastAPI):
    *   `POST /subscription` → Create new subscription.
    *   `GET /subscriptions/<customer_id>` → View subscriptions.
    *   `POST /subscription/cancel/<subscription_id>` → Cancel subscription.
    *   `GET /subscription/notifications/<customer_id>` → View notifications.
*   **NLU Integration**: Recognizes `SUBSCRIPTION_REQUEST` intents and suggests subscription options via conversational flow.

#### ✅ Example Workflow:
A customer creates a subscription for Whey Protein on Fridays. The system sets the first delivery to the next Friday and shows the confirmation. On the Wednesday or Thursday before delivery, a notification is sent. Delivery is repeated weekly unless cancelled.

#### 🌟 Benefits:
*   Hassle-free reordering.
*   Timely delivery reminders.
*   Full control and visibility over ongoing subscriptions.

### 🖼 Multimodal Interaction Capabilities

The AI supports rich multimodal communication through *Multimodal Interaction* functionality, integrating the **Gemini API** for handling visual and document-based inputs.

#### 🗣 Core Features of Multimodal Interaction

##### 1. Visual & Document Input (Gemini API)
*   **Purpose:** Enables customers to provide context through visual evidence (images, videos) or documents (PDFs) for issues like damaged products, incorrect items, or order discrepancies.
*   **Handled By:** Client-side UI (Streamlit) for file uploads and backend integration with the **Gemini API**.
*   **Logic:**
    *   Customers upload files (JPG, PNG, PDF, video) via the UI.
    *   The files are securely transmitted to the backend.
    *   The backend sends these files, potentially alongside textual complaints, to the **Gemini API**.
    *   Gemini's multimodal capabilities analyze the content (e.g., identifying damage in an image, extracting text from a PDF, or understanding events in a video).
    *   The insights derived from Gemini are used by the Autonomous Resolution Engine for intelligent validation (e.g., for refund processing) or to provide richer context to the Conversational AI.

### 🚀 Langgraph for Agent Orchestration

The project leverages **Langgraph** to build robust and stateful agent workflows for complex interactions. This allows for:
*   **Structured Decision Making:** Defining clear paths for the AI agent based on detected intent and available information.
*   **State Management:** Maintaining context across multiple turns in a conversation, crucial for multi-step processes like refund validation or subscription setup.
*   **Modular Agent Design:** Breaking down the AI's capabilities into distinct nodes (e.g., `fetch_order`, `refund_decision`, `handle_other_intents`) that can be orchestrated dynamically.

---

### 💎 Unique Value Proposition & Synergy

This system doesn’t just stack features—it orchestrates them intelligently:

*   **Visual data and natural language** are jointly used for critical decision-making (e.g., refund validation).
*   **Subscription workflows** are tied into the Autonomous Engine for automated re-payments or rescheduling.
*   **Human-in-the-Loop logic** guarantees accountability for high-risk actions.
*   Every interaction is context-aware, pulling order and user data from MongoDB to personalize responses and streamline resolution.

---

### 📈 Overall Impact

The AI-Powered Intelligent Customer Experience Platform transforms customer support into a trusted digital assistant that is:

*   **Autonomous** where possible,
*   **Proactive** with notifications and interventions,
*   **Multimodal** in understanding,
*   **Accountable** through human oversight,
*   and **Deeply personalized** via intelligent, data-driven conversation.

It dramatically reduces operational burden, boosts satisfaction, and sets a new benchmark for AI-enabled retail support systems.

---

## 🛠 Technical Stack

*   **Backend Framework:** FastAPI (Python)
*   **Frontend Framework:** Streamlit (Python)
*   **Database:** MongoDB Atlas (NoSQL Cloud Database)
*   **Conversational AI (LLM):** Groq API (`llama-3.1-8b-instant`)
*   **Multimodal AI:** Google Gemini API (`gemini-1.5-flash`)
*   **Agent Orchestration:** Langgraph
*   **Data Handling:** `motor` (async MongoDB driver)
*   **Environment Management:** `python-dotenv`
*   **HTTP Requests:** `requests`, `httpx`
*   **Data Visualization:** `plotly`
*   **Image Processing:** `Pillow`

---

## 🚀 Setup & Local Deployment

To run this project locally, follow these steps:

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd CARE
    ```

2.  **Create a virtual environment and install dependencies:**
    ```bash
    python -m venv venv
    .\venv\Scripts\activate   # On Windows
    # source venv/bin/activate # On macOS/Linux
    pip install -r src/requirements.txt
    ```

3.  **Configure Environment Variables:**
    Create a `.env` file in the root directory of the project (e.g., `CARE/.env`) with the following variables:
    ```
    GROQ_API_KEY="your_groq_api_key_here"
    GEMINI_API_KEY="your_gemini_api_key_here"
    MONGODB_URI="your_mongodb_atlas_connection_string_here"
    API_BASE_URL="http://127.0.0.1:5000" # Or your deployed FastAPI URL
    DATA_PATH="src/mock_data" # Path to initial data files for population
    ```
    *   Obtain API keys from Groq and Google Cloud (for Gemini).
    *   Set up a MongoDB Atlas cluster and get your connection string.

4.  **Populate Initial Data (Optional but Recommended):**
    This script will load sample customer, order, payment, and subscription data into your MongoDB Atlas database.
    ```bash
    python src/populate_data.py
    ```

5.  **Run the FastAPI Backend:**
    ```bash
    uvicorn src.fast_api:app --host 0.0.0.0 --port 5000 --reload
    ```
    The API will be accessible at `http://127.0.0.1:5000`.

6.  **Run the Streamlit Frontend:**
    Open a new terminal and navigate to the project root.
    ```bash
    streamlit run src/app.py
    ```
    The Streamlit application will open in your web browser, typically at `http://localhost:8501`.

---

## 💡 Usage

*   **Support Dashboard:** Interact with the AI assistant, select customers, view customer information, and see analytics. You can type messages or upload images for refund validation.
*   **Autonomous Order Planner:** Manage customer subscriptions, view upcoming deliveries, and create new recurring orders using the interactive calendar.

---

## ☁️ Deployment on Hugging Face

This project is designed for deployment on platforms like Hugging Face Spaces, leveraging FastAPI for the backend and Streamlit for the frontend. The use of MongoDB Atlas ensures persistent data storage in a cloud environment, making the application fully deployable and scalable.

---

## 🤝 Contributing

Contributions are welcome! Please feel free to fork the repository, create pull requests, or open issues for bugs and feature requests.