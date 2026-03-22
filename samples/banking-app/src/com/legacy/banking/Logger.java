package com.legacy.banking;

import java.io.FileWriter;
import java.io.IOException;
import java.text.SimpleDateFormat;
import java.util.Date;

/**
 * Utility logger for the banking system.
 * Writes to console and optionally to a file.
 * 
 * NOTE: This was written before we had log4j.
 * It works so nobody bothered replacing it.
 * TODO: Replace with proper logging framework
 * TODO: Add log levels
 * TODO: Add log rotation
 * FIXME: File handle leak on IOException
 */
public class Logger {

    private static final String LOG_FILE = "banking.log";
    private static final SimpleDateFormat DATE_FORMAT = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
    private static boolean fileLoggingEnabled = false;

    /**
     * Log a message with a level tag.
     */
    public static void log(String level, String message) {
        String timestamp = DATE_FORMAT.format(new Date());
        String logLine = String.format("[%s] [%s] %s", timestamp, level, message);
        System.out.println(logLine);

        if (fileLoggingEnabled) {
            writeToFile(logLine);
        }
    }

    /**
     * Write log line to file. 
     * Known issue: doesn't properly close the writer on exception.
     */
    private static void writeToFile(String logLine) {
        try {
            FileWriter fw = new FileWriter(LOG_FILE, true);
            fw.write(logLine + "\n");
            fw.close();
        } catch (IOException e) {
            System.err.println("Failed to write log: " + e.getMessage());
        }
    }

    // ---- Dead methods ----

    /**
     * Old method to clear the log file.
     * Dangerous and never called from production code.
     */
    public static void clearLog() {
        try {
            FileWriter fw = new FileWriter(LOG_FILE, false);
            fw.write("");
            fw.close();
        } catch (IOException e) {
            System.err.println("Failed to clear log: " + e.getMessage());
        }
    }

    /**
     * Debug dump of recent log entries. Not used.
     */
    public static void dumpRecent(int count) {
        System.out.println("Recent " + count + " log entries: [NOT IMPLEMENTED]");
    }

    public static void enableFileLogging() { fileLoggingEnabled = true; }
    public static void disableFileLogging() { fileLoggingEnabled = false; }
}
