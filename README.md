# 🛒 CARE: Customer Assistance Resolution Engine

An AI-powered intelligent customer experience platform with LangGraph agents, multimodal AI, and human-in-the-loop workflows.

## ✨ Features

- 🤖 **LangGraph Agent**: Intelligent request processing with multi-step workflows
- 🖼️ **Multimodal AI**: Image analysis for refund validation using Gemini API
- 🔄 **Human-in-the-Loop**: Escalation system for complex cases requiring human review
- 📦 **Subscription Management**: Automated recurring orders and notifications
- 📊 **Analytics Dashboard**: Real-time metrics and customer insights

## 🏗️ Architecture

```
Streamlit Frontend ←→ FastAPI Backend ←→ LangGraph Agent
                                    ↓
                            MongoDB Database
                                    ↓
                        Gemini API + Groq API
```

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- MongoDB Atlas account
- API Keys: Groq, Gemini

### Local Development
```bash
# Clone repository
git clone https://github.com/yourusername/care-engine.git
cd care-engine

# Install dependencies
pip install -r requirements.txt

# Set environment variables
# Create .env file with:
# GROQ_API_KEY=your_key
# GEMINI_API_KEY=your_key  
# MONGODB_URI=your_connection_string

# Populate sample data
python src/populate_data.py

# Run application
streamlit run streamlit_app.py
```

### Streamlit Cloud Deployment
1. Push code to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repository
4. Set environment variables in Streamlit Cloud settings
5. Deploy!

### Hugging Face Spaces Deployment
1. Create new Space on [huggingface.co/spaces](https://huggingface.co/spaces)
2. Choose SDK: Streamlit
3. Upload files or connect GitHub
4. Set environment variables in Space settings
5. Your app will be live!

## 🧪 Test Scenarios

1. **Refund Request**: "I want a refund for order ORD001, it was damaged"
2. **Order Status**: "What is the status of order ORD002?"
3. **Image Upload**: Upload damage photo for automatic validation
4. **Human Review**: Cases with low AI confidence get escalated

## �  Project Structure

```
care-engine/
├── streamlit_app.py          # Main Streamlit application
├── src/
│   ├── fast_api.py          # FastAPI backend
│   ├── resolution_engine.py # LangGraph agent
│   ├── nlu_pipeline.py      # Intent classification
│   ├── data_handler.py      # MongoDB operations
│   ├── subscription_manager.py # Subscription logic
│   ├── populate_data.py     # Sample data setup
│   └── mock_data/          # Sample JSON data
├── requirements.txt         # Dependencies
├── Dockerfile              # Container setup
└── README.md               # This file
```

## 🔧 Environment Variables

```env
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
MONGODB_URI=your_mongodb_atlas_connection_string
```

## 🎯 How It Works

1. **Customer Request**: User selects customer and sends message/uploads image
2. **Intent Classification**: Groq API classifies the request intent
3. **LangGraph Processing**: Agent workflow processes the request
4. **AI Decision**: High confidence → Auto-resolve, Low confidence → Escalate
5. **Human Review**: Agents review escalated cases and make final decisions
6. **Resolution**: Customer receives response and wallet updates

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License.

---

**CARE** - Transforming customer support with AI-powered intelligence! 🚀