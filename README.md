# FRIDAY AI 🤖

**A Personal AI Desktop Assistant Inspired by Marvel's FRIDAY**

FRIDAY AI is a Python-based personal desktop assistant designed to make computer interaction more intelligent and intuitive. Inspired by the AI assistant from Marvel's Iron Man, this project combines local language models, voice interaction, memory, computer vision, and a visual dashboard to create a personalized AI experience.

The project aims to provide AI-powered assistance while making use of locally running models through Ollama.

## ✨ Features

- **AI Conversations:** Interact with local language models for AI-powered responses.
- **Voice Interaction:** Communicate with the assistant using speech recognition and text-to-speech.
- **Personalized Assistant:** Uses the name FRIDAY and supports personalized interactions.
- **Memory System:** Stores selected information to support contextual and personalized interactions.
- **Face Recognition:** Uses computer vision to identify recognized faces.
- **Desktop Context Awareness:** Designed to capture screen context to help the assistant understand the current desktop environment.
- **Web Dashboard:** Includes a visual dashboard for presenting information and assistant-related features.
- **Local AI Models:** Uses Ollama to run supported AI models locally.

*Note: Feature availability may vary depending on the current implementation.*

## 🛠️ Tech Stack

| Technology | Purpose |
|---|---|
| Python | Core application logic |
| Ollama | Running local AI models |
| Llama 3.1 | Language model for conversations |
| LLaVA | Vision-language model |
| SpeechRecognition | Speech input |
| pyttsx3 | Text-to-speech |
| OpenCV | Computer vision |
| face_recognition | Face recognition |
| HTML | Dashboard interface |
| PyAutoGUI | Desktop interaction and automation |
| MSS | Screen capture |

## 💻 Requirements

- Windows PC
- Python 3.11
- [Ollama](https://ollama.com/)
- Git
- [Visual Studio Code](https://code.visualstudio.com/) (recommended)
- Microphone for voice input
- Webcam if using face-recognition features
- Compatible hardware for running local AI models

Performance depends on the selected models and available system resources.

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Lakshay3010/FRIDAY-AI.git
cd FRIDAY-AI
```

Replace the repository URL if your actual GitHub repository uses a different name.

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it in Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

If the repository includes a `requirements.txt` file:

```bash
pip install -r requirements.txt
```

If it doesn't, install the dependencies listed in your project's actual setup instructions. Some packages, especially face-recognition dependencies, may require additional system components.

### 4. Install Ollama models

Install Ollama from its official website, then download the models used by your configuration:

```bash
ollama pull llama3.1:8b
ollama pull llava:7b
```

Ensure the models are compatible with your available RAM and GPU memory.

### 5. Run FRIDAY AI

Run the Python entry-point file for your project. For example:

```bash
python main.py
```

Replace `main.py` with the actual entry-point filename in your repository.

## 📁 Project Structure

The project may contain components similar to these:

```text
FRIDAY-AI/
├── main.py
├── requirements.txt
├── friday_dashboard.html
├── memory.json
├── faces/
├── .gitignore
└── README.md
```

This is an illustrative structure, not a verified listing of your current files. Update it to match the actual repository before publishing.

## 🔒 Privacy and Security

- Local model inference can reduce reliance on external AI services.
- Some features may access your microphone, camera, screen, or desktop.
- Avoid committing API keys, passwords, personal memory files, face-recognition data, or other sensitive information.
- Review your `.gitignore` before pushing code to GitHub.
- Check the privacy implications of any external services or integrations you enable.

## 🗺️ Roadmap

Potential improvements include:

- [ ] More natural voice conversations
- [ ] Improved long-term memory management
- [ ] More reliable desktop automation
- [ ] Expanded dashboard functionality
- [ ] Better error handling and recovery
- [ ] Easier installation and configuration
- [ ] Improved privacy controls

## 👨‍💻 Developer

**Lakshay Verma**

GitHub: [@Lakshay3010](https://github.com/Lakshay3010)

## 📄 License

No license has been specified yet. Add a `LICENSE` file if you decide to distribute the project under an open-source license.

---

*FRIDAY AI is an independent personal project inspired by the fictional assistant from Marvel. It is not affiliated with or endorsed by Marvel or Disney.*
