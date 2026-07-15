const { app, BrowserWindow, Menu, dialog, screen, shell } = require("electron");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");

const APP_NAME = "LumaLyrics";
const ROOT_DIR = path.resolve(__dirname, "..");
const EXTERNAL_PROJECT_DIR = path.resolve(ROOT_DIR, "..", "..", "..", "..", "..", "..");
const ICON_PATH = path.join(ROOT_DIR, "build", "icon.png");
const BASE_PORT = Number(process.env.LYRIC_WIDGET_PORT || "5001");

let flaskProcess = null;
let mainWindow = null;
let fitTimer = null;
let activePort = BASE_PORT;
const WIDGET_WIDTH = 430;
const WIDGET_DEFAULT_HEIGHT = 620;
const WIDGET_MIN_WIDTH = 360;
const WIDGET_MIN_HEIGHT = 540;
const WIDGET_HEIGHT_PADDING = 8;

function logStartup(message) {
  try {
    const logPath = path.join(app.getPath("userData"), "startup.log");
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    fs.appendFileSync(logPath, `[${new Date().toISOString()}] ${message}\n`);
  } catch {
    fs.appendFileSync("/private/tmp/lyric-widget-startup.log", `[${new Date().toISOString()}] ${message}\n`);
  }
}

function appUrl(route = "") {
  return `http://127.0.0.1:${activePort}${route}`;
}

async function fitWidgetWindowToContent() {
  if (!mainWindow || mainWindow.isDestroyed()) return;

  try {
    const contentHeight = await mainWindow.webContents.executeJavaScript(
      `Math.ceil(document.querySelector(".widget-shell")?.scrollHeight || document.body.scrollHeight || ${WIDGET_DEFAULT_HEIGHT})`,
    );
    const display = screen.getDisplayMatching(mainWindow.getBounds());
    const maxHeight = Math.max(WIDGET_MIN_HEIGHT, display.workArea.height - 56);
    const nextHeight = Math.min(
      maxHeight,
      Math.max(WIDGET_MIN_HEIGHT, (Number(contentHeight) || WIDGET_DEFAULT_HEIGHT) + WIDGET_HEIGHT_PADDING),
    );
    const [currentWidth, currentHeight] = mainWindow.getContentSize();

    if (Math.abs(currentHeight - nextHeight) > 8 || currentWidth < WIDGET_WIDTH) {
      mainWindow.setContentSize(Math.max(currentWidth, WIDGET_WIDTH), nextHeight, true);
    }
  } catch (error) {
    logStartup(`Could not fit widget window: ${error.message}`);
  }
}

function requestStatus(url, timeoutMs = 500) {
  return new Promise((resolve) => {
    const request = http.get(url, (response) => {
      response.resume();
      resolve(response.statusCode || 0);
    });

    request.on("error", () => resolve(0));
    request.setTimeout(timeoutMs, () => {
      request.destroy();
      resolve(0);
    });
  });
}

async function isHealthyServer(port) {
  const baseUrl = `http://127.0.0.1:${port}`;
  const [widgetStatus, cssStatus, jsStatus] = await Promise.all([
    requestStatus(`${baseUrl}/widget`),
    requestStatus(`${baseUrl}/static/widget.css`),
    requestStatus(`${baseUrl}/static/widget.js`),
  ]);
  return widgetStatus === 200 && cssStatus === 200 && jsStatus === 200;
}

function isPortFree(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => {
      server.close(() => resolve(true));
    });
    server.listen(port, "127.0.0.1");
  });
}

async function findFreePort(startPort) {
  for (let candidate = startPort; candidate < startPort + 20; candidate += 1) {
    if (await isPortFree(candidate)) {
      return candidate;
    }
  }
  throw new Error("No free local port was found for the lyric server.");
}

async function waitForServer(timeoutMs = 10000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await isHealthyServer(activePort)) {
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return false;
}

function pythonCommand() {
  const candidates = [
    process.env.LYRIC_WIDGET_PYTHON,
    path.join(EXTERNAL_PROJECT_DIR, ".venv", "bin", "python"),
    path.join(ROOT_DIR, ".venv", "bin", "python"),
    "python3",
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (candidate !== "python3" && !fs.existsSync(candidate)) {
      continue;
    }

    const result = spawnSync(candidate, ["-c", "import flask"], {
      cwd: fs.existsSync(EXTERNAL_PROJECT_DIR) ? EXTERNAL_PROJECT_DIR : ROOT_DIR,
      encoding: "utf8",
      timeout: 3000,
    });
    if (result.status === 0) {
      return candidate;
    }
  }

  return "python3";
}

function dotenvPath() {
  const candidates = [
    path.join(ROOT_DIR, ".env"),
    path.join(process.cwd(), ".env"),
    path.resolve(ROOT_DIR, "..", "..", "..", "..", "..", "..", ".env"),
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || path.join(ROOT_DIR, ".env");
}

async function startFlaskIfNeeded() {
  if (await isHealthyServer(activePort)) {
    logStartup(`Using existing lyric server at ${appUrl("/")}`);
    return;
  }

  if (!(await isPortFree(activePort))) {
    logStartup(`Port ${activePort} is occupied by a non-widget server; finding another port.`);
    activePort = await findFreePort(activePort + 1);
  }

  const python = pythonCommand();
  logStartup(`Starting Flask with ${python} on port ${activePort}`);
  flaskProcess = spawn(
    python,
    ["-m", "flask", "--app", "app", "run", "--port", String(activePort), "--no-debugger", "--no-reload"],
    {
      cwd: ROOT_DIR,
      env: {
        ...process.env,
        FLASK_DEBUG: "0",
        LYRIC_TRANSLATOR_ENV: dotenvPath(),
        TRANSLATION_CACHE_PATH:
          process.env.TRANSLATION_CACHE_PATH || path.join(app.getPath("userData"), "translations.sqlite3"),
        PYTHONPYCACHEPREFIX: "/private/tmp/music-translator-pycache",
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  flaskProcess.stdout.on("data", (data) => logStartup(`flask stdout: ${data.toString().trim()}`));
  flaskProcess.stderr.on("data", (data) => logStartup(`flask stderr: ${data.toString().trim()}`));
  flaskProcess.on("error", (error) => {
    logStartup(`Flask spawn error: ${error.message}`);
  });
  flaskProcess.on("exit", () => {
    logStartup("Flask process exited.");
    flaskProcess = null;
  });

  const isReady = await waitForServer();
  if (!isReady) {
    throw new Error("The local lyric server did not start.");
  }
}

function createMenu() {
  Menu.setApplicationMenu(
    Menu.buildFromTemplate([
      {
        label: APP_NAME,
        submenu: [
          {
            label: "Open Full View",
            click: () => shell.openExternal(appUrl("")),
          },
          {
            label: "Open Focus Mode",
            click: () => shell.openExternal(appUrl("/focus")),
          },
          { type: "separator" },
          { role: "quit" },
        ],
      },
      {
        label: "View",
        submenu: [
          { role: "reload" },
          { role: "toggleDevTools" },
          { type: "separator" },
          { role: "resetZoom" },
          { role: "zoomIn" },
          { role: "zoomOut" },
        ],
      },
    ]),
  );
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: WIDGET_WIDTH,
    height: WIDGET_DEFAULT_HEIGHT,
    minWidth: WIDGET_MIN_WIDTH,
    minHeight: WIDGET_MIN_HEIGHT,
    title: APP_NAME,
    icon: ICON_PATH,
    alwaysOnTop: true,
    backgroundColor: "#101010",
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadURL(appUrl("/widget"));
  mainWindow.webContents.on("did-finish-load", () => {
    fitWidgetWindowToContent();
    setTimeout(fitWidgetWindowToContent, 700);
    setTimeout(fitWidgetWindowToContent, 1800);
    setTimeout(fitWidgetWindowToContent, 3600);
    if (fitTimer) {
      clearInterval(fitTimer);
    }
    fitTimer = setInterval(fitWidgetWindowToContent, 1200);
    setTimeout(() => {
      if (fitTimer) {
        clearInterval(fitTimer);
        fitTimer = null;
      }
    }, 12000);
  });
  mainWindow.on("closed", () => {
    if (fitTimer) {
      clearInterval(fitTimer);
      fitTimer = null;
    }
  });
  mainWindow.once("ready-to-show", () => {
    fitWidgetWindowToContent();
    mainWindow.show();
  });
}

app.whenReady().then(async () => {
  try {
    app.setName(APP_NAME);
    if (process.platform === "darwin" && app.dock && fs.existsSync(ICON_PATH)) {
      app.dock.setIcon(ICON_PATH);
    }
    createMenu();
    await startFlaskIfNeeded();
    createWindow();
  } catch (error) {
    logStartup(`Startup failed: ${error.stack || error.message}`);
    dialog.showErrorBox(`${APP_NAME} could not open`, error.message);
    app.quit();
    return;
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  if (flaskProcess) {
    flaskProcess.kill();
  }
});
