const path = require('path');

function getPythonPaths() {
    const isWindows = process.platform === 'win32';
    
    const pythonExecutable = isWindows
        ? path.join(__dirname, '../../../.venv/Scripts/python.exe')
        : path.join(__dirname, '../../../../../.venv/bin/python');

    const scriptPath = path.join(__dirname, '../../browser/worker_taqeem.py')
    const scriptDir = path.dirname(scriptPath);

    return {
        pythonExecutable,
        scriptPath,
        scriptDir
    };
}

module.exports = {
    getPythonPaths
};