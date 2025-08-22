# Amazon Invoice Downloader

[![PyPI - Version](https://img.shields.io/pypi/v/amazon-invoice-downloader.svg)](https://pypi.org/project/amazon-invoice-downloader)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/amazon-invoice-downloader.svg)](https://pypi.org/project/amazon-invoice-downloader)

-----

**Table of Contents**

- [What it does](#what-it-does)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [AI Assistant Integration & Debugging](#ai-assistant-integration--debugging)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## What it does

This program automates downloading Amazon purchase invoices using [Playwright](https://playwright.dev/) to control a Chromium browser. It logs into Amazon, navigates to "Returns & Orders", and downloads invoices for a specified date range.

⚠️ **Important Note**: This program was last tested and verified to work in August 2025. Amazon.com occasionally updates their website interface, which may require code updates to maintain compatibility. If you encounter issues, please consider submitting a pull request with fixes.

**Credentials** (in order of precedence):
1. Command line: `--email=<email> --password=<password>`
2. Environment variables: `$AMAZON_EMAIL` and `$AMAZON_PASSWORD`
3. `.env` file (auto-loaded from current/parent directories)

**Date Range**: Use `--year=<YYYY>` or `--date-range=<YYYYMMDD-YYYYMMDD>`. Defaults to current year.

**Output**: PDFs saved to `./downloads/` as `YYYYMMDD_<total>_amazon_<orderid>.pdf`. Existing files are skipped.

**Features**:
- Human-like delays (2-5 seconds) to avoid bot detection
- Automatic credential loading from .env files or environment variables
- Remote debugging enabled on port 9222 for AI assistant integration
- Virtual authenticator configured to prevent passkey dialogs
- Stealth mode enabled to avoid detection
- Automatic 2FA detection and handling
- Skips cancelled orders automatically
- Creates downloads/ directory automatically



## Installation

### Option 1: Using pip

```bash
pip install amazon-invoice-downloader
playwright install
```

### Option 2: Development Installation

```bash
# Clone the repository
git clone https://github.com/dcwangmit01/amazon-invoice-downloader.git
cd amazon-invoice-downloader

# Install dependencies using uv
make deps

# Or manually with uv
uv venv
uv sync
uv run playwright install
```

## Quick Start

1. **Set up credentials** (choose one method):
   ```bash
   # Option A: Create a .env file (recommended)
   echo "AMAZON_EMAIL=your_email@example.com" > .env
   echo "AMAZON_PASSWORD=your_password_here" >> .env

   # Option B: Set environment variables
   export AMAZON_EMAIL=your_email@example.com
   export AMAZON_PASSWORD=your_password_here

   # Option C: Use command line arguments
   amazon-invoice-downloader --email=your_email@example.com --password=your_password
   ```

2. **Run the downloader**:
   ```bash
   # Download invoices for current year
   amazon-invoice-downloader

   # Download invoices for specific year
   amazon-invoice-downloader --year=2023

   # Download invoices for date range
   amazon-invoice-downloader --date-range=20230101-20231231
   ```

**Note:** The program automatically searches for `.env` files in the current directory and up to 3 parent directories. The `.env` file is already in `.gitignore` to prevent accidentally committing sensitive credentials.



## Usage

### What Happens When You Run It

1. **Browser Launch**: The program launches a Chromium browser with remote debugging on port 9222
2. **Stealth Setup**: Configures stealth mode and virtual authenticator to avoid detection
3. **Login Process**: Navigates to Amazon and attempts to log in using your credentials
4. **2FA Handling**: If 2FA is detected, the program pauses and prompts you to complete it manually
5. **Invoice Download**: Downloads invoices for the specified date range to `./downloads/`
6. **File Naming**: Saves files as `YYYYMMDD_<total>_amazon_<orderid>.pdf`

### Common Scenarios

**CAPTCHA/Login Issues**: Amazon may detect automation and require manual intervention. Simply complete the CAPTCHA or login process in the browser window, and the script will continue automatically.

**2FA Authentication**: If you have 2FA enabled, the program will detect this and wait for you to complete the authentication in the browser.

**Browser Control**: You can manually control the browser at any time. The automation will resume once you're done.

```console
$ amazon-invoice-downloader -h
Amazon Invoice Downloader

Usage:
  amazon-invoice-downloader \
    [--email=<email> --password=<password>] \
    [--year=<YYYY> | --date-range=<YYYYMMDD-YYYYMMDD>]
  amazon-invoice-downloader (-h | --help)
  amazon-invoice-downloader (-v | --version)

Login Options:
  --email=<email>          Amazon login email  [default: $AMAZON_EMAIL].
  --password=<password>    Amazon login password  [default: $AMAZON_PASSWORD].

Date Range Options:
  --date-range=<YYYYMMDD-YYYYMMDD>  Start and end date range
  --year=<YYYY>                     Year, formatted as YYYY  [default: <CUR_YEAR>].

Options:
  -h --help                Show this screen.
  -v --version             Show version.

Features:
  - Remote debugging enabled on port 9222 for AI MCP Servers
  - Virtual authenticator configured to prevent passkey dialogs
  - Stealth mode enabled to avoid detection

Credential Precedence:
  1. Command line arguments (--email, --password)
  2. Environment variables ($AMAZON_EMAIL, $AMAZON_PASSWORD)
  3. .env file (automatically loaded if env vars not set)

Examples:
  amazon-invoice-downloader --year=2022  # Uses .env file or env vars $AMAZON_EMAIL and $AMAZON_PASSWORD
  amazon-invoice-downloader --date-range=20220101-20221231
  amazon-invoice-downloader --email=user@example.com --password=secret  # Defaults to current year
  amazon-invoice-downloader --email=user@example.com --password=secret --year=2022
  amazon-invoice-downloader --email=user@example.com --password=secret --date-range=20220101-20221231
```

## AI Assistant Integration & Debugging

This program is designed to work seamlessly with AI assistants through the Model Context Protocol (MCP). The browser automatically launches with remote debugging capabilities that allow AI assistants to monitor and control the automation process.

### How It Works

1. **Automatic CDP Setup**: The program launches Chromium with Chrome DevTools Protocol (CDP) enabled on port 9222
2. **MCP Server Configuration**: The `.cursor/mcp.json` file configures the Playwright MCP server to connect to the browser
3. **Real-time Control**: AI assistants can take control of the browser session when needed

### Setup for AI Assistant MCP Control

1. **Install the Playwright MCP Server**:
   ```bash
   npm install -g @playwright/mcp
   ```

2. **Configure MCP in Cursor**:
   The `.cursor/mcp.json` file is already configured with:
   ```json
   {
     "mcpServers": {
       "Playwright": {
         "command": "npx @playwright/mcp@latest",
         "args": ["--cdp-endpoint=http://localhost:9222"],
         "env": {"DEBUG": "pw:mcp"}
       }
     }
   }
   ```

3. **Run the Program**:
   ```bash
   amazon-invoice-downloader --year=2024
   ```

4. **AI Assistant Control**: Once the browser launches with remote debugging, AI MCP assistants can:
   - Monitor the browser session in real-time
   - Handle CAPTCHA challenges automatically
   - Complete 2FA authentication when prompted
   - Debug automation issues and failures
   - Take manual control when needed
   - Resume automation after manual intervention



### Troubleshooting AI Integration

- **Port 9222 Already in Use**: Ensure no other Chrome instances are using the debugging port
- **MCP Connection Failed**: Verify the Playwright MCP server is installed and the `.cursor/mcp.json` configuration is correct
- **Authentication Issues**: AI assistants can help complete CAPTCHA or 2FA challenges when they appear
- **Browser Crashes**: The program will automatically reconnect to the browser session

### Security Considerations

- The browser launches with `--disable-web-security` for automation purposes
- Remote debugging is bound to `localhost` only for security
- Virtual authenticator prevents passkey dialogs that could interfere with automation
- Stealth mode helps avoid detection by Amazon's bot detection systems

## Development

### Prerequisites

- **Python 3.12+**: Required for running the application
- **[uv](https://docs.astral.sh/uv/)**: Fast Python package manager (replaces pip/poetry)
- **[Make](https://www.gnu.org/software/make/)**: For development commands
- **macOS**: The Makefile is optimized for macOS with Homebrew (Linux users can adapt manually)
- **Node.js**: Optional, only needed for AI assistant MCP integration

### Development Setup

```bash
# Clone the repository
git clone https://github.com/dcwangmit01/amazon-invoice-downloader.git
cd amazon-invoice-downloader

# Set up development environment
make deps

# Install pre-commit hooks
make deps-dev
```

### Available Make Commands

```bash
# Show all available commands
make help

# Set up complete development environment (macOS only)
make deps

# Set up just the uv environment
make deps-uv

# Install development tools (pre-commit hooks)
make deps-dev

# Install the program in the current environment
make install-local

# Run tests
make test

# Format and lint code (auto-fixes issues)
make format

# Check code quality (runs pre-commit)
make check

# Run the program locally (help)
make run-local

# Run example commands
make run

# Build the project
make build

# Clean the project
make clean

# Complete clean (removes .venv and uv.lock)
make mrclean
```

### Testing

```bash
# Run all tests
make test

# Run with coverage
uv run pytest --cov=amazon_invoice_downloader

# Run specific test file
uv run pytest tests/test_specific.py
```

### Code Quality

```bash
# Format code
uv run black .

# Lint code
uv run flake8 src/amazon_invoice_downloader tests

# Run pre-commit checks
uv run pre-commit run --all-files
```

## Troubleshooting

### Common Issues

**Browser Fails to Launch**:
- Ensure Playwright browsers are installed: `uv run playwright install`
- Check if port 9222 is already in use: `lsof -i :9222`

**Login Issues**:
- Amazon may require CAPTCHA - complete it manually in the browser
- Check your credentials are correct
- Ensure 2FA is handled manually when prompted

**Download Failures**:
- Check if the `downloads/` directory exists and is writable
- Verify your Amazon account has access to order history
- Some orders may not have invoices available

**Playwright Issues**:
- Update Playwright: `uv run playwright install`
- Clear browser data if login persists failing

### Getting Help

- **GitHub Issues**: Report bugs at the project repository
- **Logs**: The program outputs detailed console logs during execution
- **Browser Debugging**: Use `http://localhost:9222` to inspect the browser state
- **AI Assistant**: Use MCP integration for real-time debugging assistance

## License

`amazon-invoice-downloader` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
