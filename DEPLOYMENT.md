# 🚀 CARE Deployment Guide

## 📋 Quick Deployment Steps

### 1. **Streamlit Cloud** (Recommended)

1. **Push to GitHub**:
   ```bash
   git add .
   git commit -m "Initial commit"
   git push origin main
   ```

2. **Deploy on Streamlit Cloud**:
   - Go to [share.streamlit.io](https://share.streamlit.io)
   - Click "New app"
   - Connect your GitHub repository
   - Set main file: `streamlit_app.py`
   - Add environment variables:
     ```
     GROQ_API_KEY=your_key_here
     GEMINI_API_KEY=your_key_here
     MONGODB_URI=your_connection_string
     ```
   - Click "Deploy"

3. **Your app will be live at**: `https://your-app-name.streamlit.app`

### 2. **Hugging Face Spaces**

1. **Create Space**:
   - Go to [huggingface.co/spaces](https://huggingface.co/spaces)
   - Click "Create new Space"
   - Choose SDK: "Streamlit"
   - Name: "care-engine"

2. **Upload Files**:
   - Upload all project files
   - Or connect your GitHub repository

3. **Set Environment Variables**:
   - Go to Space settings
   - Add the same environment variables as above

4. **Your app will be live at**: `https://huggingface.co/spaces/username/care-engine`

## 🔧 Environment Variables Required

```env
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/care_db
```

## 📁 Files to Deploy

Essential files only:
- `streamlit_app.py` (main app)
- `src/` folder (all backend code)
- `requirements.txt`
- `Dockerfile` (for containerized deployment)
- `README.md`

## ✅ Deployment Checklist

- [ ] Code pushed to GitHub
- [ ] Environment variables configured
- [ ] MongoDB Atlas database accessible
- [ ] API keys have sufficient quotas
- [ ] Sample data populated (run `python src/populate_data.py`)

That's it! Your CARE system will be live and accessible worldwide! 🌍