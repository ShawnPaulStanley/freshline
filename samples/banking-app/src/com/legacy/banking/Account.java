package com.legacy.banking;

import java.util.ArrayList;
import java.util.List;
import java.util.Date;

/**
 * Core Account class for the legacy banking system.
 * This class manages customer bank accounts with basic operations.
 * 
 * TODO: Refactor this to use modern Java streams
 * TODO: Add proper exception handling
 * NOTE: This was originally written in 2003 by Dave
 * FIXME: The balance calculation might have rounding issues
 */
public class Account {
    private String accountId;
    private String ownerName;
    private double balance;
    private List<Transaction> transactionHistory;
    private AccountType type;
    private Date createdDate;
    private boolean isActive;

    // Old constants - some might not be used anymore
    private static final double MIN_BALANCE = 100.0;
    private static final double MAX_WITHDRAWAL = 10000.0;
    private static final double LEGACY_FEE = 2.50;  // Nobody uses this anymore
    private static final int MAX_DAILY_TRANSACTIONS = 50;  // Dead constant

    public Account(String accountId, String ownerName, double initialBalance, AccountType type) {
        this.accountId = accountId;
        this.ownerName = ownerName;
        this.balance = initialBalance;
        this.transactionHistory = new ArrayList<>();
        this.type = type;
        this.createdDate = new Date();
        this.isActive = true;
    }

    /**
     * Deposit money into the account.
     * Creates a transaction record and updates balance.
     */
    public boolean deposit(double amount) {
        if (amount <= 0) {
            Logger.log("ERROR", "Invalid deposit amount: " + amount);
            return false;
        }
        if (!isActive) {
            Logger.log("ERROR", "Account " + accountId + " is inactive");
            return false;
        }

        this.balance += amount;
        Transaction txn = new Transaction(
            TransactionType.DEPOSIT, amount, this.balance, "Deposit"
        );
        transactionHistory.add(txn);
        Logger.log("INFO", "Deposited " + amount + " to account " + accountId);
        return true;
    }

    /**
     * Withdraw money from the account.
     * Validates sufficient balance and withdrawal limits.
     */
    public boolean withdraw(double amount) {
        if (amount <= 0) {
            Logger.log("ERROR", "Invalid withdrawal amount: " + amount);
            return false;
        }
        if (amount > MAX_WITHDRAWAL) {
            Logger.log("ERROR", "Exceeds max withdrawal limit: " + amount);
            return false;
        }
        if (this.balance - amount < MIN_BALANCE) {
            Logger.log("ERROR", "Insufficient balance for withdrawal");
            return false;
        }

        this.balance -= amount;
        Transaction txn = new Transaction(
            TransactionType.WITHDRAWAL, amount, this.balance, "Withdrawal"
        );
        transactionHistory.add(txn);
        Logger.log("INFO", "Withdrew " + amount + " from account " + accountId);
        return true;
    }

    /**
     * Transfer money to another account.
     * Uses withdraw and deposit internally.
     */
    public boolean transfer(Account target, double amount) {
        if (target == null) {
            Logger.log("ERROR", "Target account is null");
            return false;
        }

        boolean withdrawn = this.withdraw(amount);
        if (withdrawn) {
            boolean deposited = target.deposit(amount);
            if (!deposited) {
                // Rollback: put the money back
                this.balance += amount;
                Logger.log("ERROR", "Transfer failed, rolling back");
                return false;
            }
            Transaction txn = new Transaction(
                TransactionType.TRANSFER, amount, this.balance,
                "Transfer to " + target.getAccountId()
            );
            transactionHistory.add(txn);
            Logger.log("INFO", "Transferred " + amount + " to " + target.getAccountId());
            return true;
        }
        return false;
    }

    /**
     * Calculate interest based on account type.
     * Uses the InterestCalculator utility.
     */
    public double calculateInterest() {
        double rate = InterestCalculator.getRate(this.type);
        double interest = this.balance * rate;
        return interest;
    }

    /**
     * Apply monthly interest to the account.
     */
    public void applyMonthlyInterest() {
        double interest = calculateInterest() / 12.0;
        deposit(interest);
        Logger.log("INFO", "Applied monthly interest: " + interest);
    }

    // ========================================
    // DEAD CODE SECTION - Nobody calls these
    // ========================================

    /**
     * Old method for printing statement to console.
     * Replaced by StatementGenerator but never removed.
     */
    public void printStatement() {
        System.out.println("=== Account Statement ===");
        System.out.println("Account: " + accountId);
        System.out.println("Owner: " + ownerName);
        System.out.println("Balance: $" + balance);
        for (Transaction t : transactionHistory) {
            System.out.println(t.toString());
        }
    }

    // /** 
    //  * Legacy fee calculation - commented out but left here
    //  * This was used before we moved to the new fee schedule
    //  */
    // public double calculateLegacyFee() {
    //     return LEGACY_FEE * transactionHistory.size();
    // }
    //
    // public void applyLegacyFee() {
    //     double fee = calculateLegacyFee();
    //     this.balance -= fee;
    // }

    /**
     * Debug method for internal testing. Not part of production flow.
     */
    private void debugDump() {
        System.out.println("DEBUG: " + accountId + " | " + balance + " | " + transactionHistory.size());
    }

    // Getters and Setters
    public String getAccountId() { return accountId; }
    public String getOwnerName() { return ownerName; }
    public double getBalance() { return balance; }
    public List<Transaction> getTransactionHistory() { return transactionHistory; }
    public AccountType getType() { return type; }
    public boolean isActive() { return isActive; }
    public void setActive(boolean active) { this.isActive = active; }
}
