package com.legacy.banking;

import java.util.Date;

/**
 * Represents a single banking transaction.
 * Immutable record of account activity.
 */
public class Transaction {
    private String transactionId;
    private TransactionType type;
    private double amount;
    private double balanceAfter;
    private String description;
    private Date timestamp;

    // Legacy counter - never actually read anywhere
    private static int globalCounter = 0;

    public Transaction(TransactionType type, double amount, double balanceAfter, String description) {
        this.transactionId = generateId();
        this.type = type;
        this.amount = amount;
        this.balanceAfter = balanceAfter;
        this.description = description;
        this.timestamp = new Date();
    }

    private String generateId() {
        globalCounter++;
        return "TXN-" + System.currentTimeMillis() + "-" + globalCounter;
    }

    /**
     * Format transaction for display.
     */
    public String format() {
        return String.format("[%s] %s: $%.2f | Balance: $%.2f | %s",
            timestamp.toString(), type.name(), amount, balanceAfter, description);
    }

    // TODO: Add serialization support
    // TODO: Add currency conversion
    // TODO: This whole class needs refactoring honestly
    // HACK: Quick fix for the reporting module

    @Override
    public String toString() {
        return format();
    }

    // ---- Dead methods below ----

    /**
     * Legacy XML export. Nobody uses XML anymore.
     */
    public String toXml() {
        return "<transaction>" +
               "<id>" + transactionId + "</id>" +
               "<type>" + type + "</type>" +
               "<amount>" + amount + "</amount>" +
               "</transaction>";
    }

    /**
     * Legacy comparison method. Collections.sort uses Comparable now.
     */
    public int compareTo(Transaction other) {
        return this.timestamp.compareTo(other.timestamp);
    }

    // Getters
    public String getTransactionId() { return transactionId; }
    public TransactionType getType() { return type; }
    public double getAmount() { return amount; }
    public double getBalanceAfter() { return balanceAfter; }
    public String getDescription() { return description; }
    public Date getTimestamp() { return timestamp; }
}
