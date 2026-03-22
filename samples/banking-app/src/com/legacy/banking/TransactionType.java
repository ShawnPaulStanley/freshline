package com.legacy.banking;

/**
 * Transaction type enumeration.
 */
public enum TransactionType {
    DEPOSIT,
    WITHDRAWAL,
    TRANSFER,
    FEE,           // Dead - no longer charged
    INTEREST,
    ADJUSTMENT     // Dead - never used
}
