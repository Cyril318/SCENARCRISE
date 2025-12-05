# CrisisSim AI

CrisisSim AI is a scenario simulation application built with Python and Streamlit. It allows users to navigate through branching scenarios, make choices with consequences, and visualize the impact on various metrics.

## Features

- **Scenario Engine**: Manages session state, scoring, and navigation.
- **Timer System**: Enforces time limits per node, automatically selecting a default choice if time runs out.
- **Data Support**: Load scenarios from JSON or CSV files.
- **AI Integration**: (Optional) Generate scenarios using Google Gemini.
- **Interface**: Clean, 4-block layout with branding, context, images, and choices.

## Installation

1. Clone the repository.
2. Install the required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## Usage

To launch the application, run the following command in your terminal:

```bash
streamlit run app.py
```

### Loading Scenarios

Once the app is running:
1. Open the **Sidebar**.
2. Select **Load Mode**:
   - **Upload Files**: Upload your own JSON or CSV files.
   - **Use Sample Data**: Quickly load the built-in demo scenario.
   - **Generate with AI**: Provide a description to generate a new scenario (requires Gemini API Key).

### CSV Format

If loading from CSV, ensure your files match the expected format.
- **Nodes CSV**: Can support multiple impacts per choice using the format `category:value;category2:value2`.

## Requirements

- Python 3.8+
- Streamlit
- Google Generative AI
