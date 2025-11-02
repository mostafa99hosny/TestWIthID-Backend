class CommandHandler {
    constructor() {
        this.pendingCommands = new Map();
        this.commandId = 0;
    }

    generateCommandId() {
        return this.commandId++;
    }

    registerCommand(commandId, resolve, reject) {
        this.pendingCommands.set(commandId, { resolve, reject });
    }

    resolveCommand(commandId, result) {
        const handler = this.pendingCommands.get(commandId);
        if (handler) {
            handler.resolve(result);
            this.pendingCommands.delete(commandId);
            return true;
        }
        return false;
    }

    rejectCommand(commandId, error) {
        const handler = this.pendingCommands.get(commandId);
        if (handler) {
            handler.reject(error);
            this.pendingCommands.delete(commandId);
            return true;
        }
        return false;
    }

    rejectAllCommands(error) {
        this.pendingCommands.forEach((handler) => {
            handler.reject(error);
        });
        this.pendingCommands.clear();
    }

    getPendingCount() {
        return this.pendingCommands.size;
    }
}

module.exports = CommandHandler;