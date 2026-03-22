package com.legacy.banking;

import java.util.HashMap;
import java.util.Map;
import java.util.List;
import java.util.ArrayList;

/**
 * Main entry point for the legacy banking application.
 * Manages all accounts and provides top-level operations.
 */
public class BankingApp {

    private Map<String, Account> accounts;
    private int nextAccountId;

    public BankingApp() {
        this.accounts = new HashMap<>();
        this.nextAccountId = 1000;
    }

    /**
     * Create a new bank account.
     */
    public Account createAccount(String ownerName, double initialBalance, AccountType type) {
        String id = "ACC-" + nextAccountId++;
        Account account = new Account(id, ownerName, initialBalance, type);
        accounts.put(id, account);
        Logger.log("INFO", "Created account " + id + " for " + ownerName);
        return account;
    }

    /**
     * Find account by ID.
     */
    public Account getAccount(String accountId) {
        Account account = accounts.get(accountId);
        if (account == null) {
            Logger.log("ERROR", "Account not found: " + accountId);
        }
        return account;
    }

    /**
     * Close an account - sets it inactive.
     */
    public boolean closeAccount(String accountId) {
        Account account = getAccount(accountId);
        if (account != null) {
            account.setActive(false);
            Logger.log("INFO", "Closed account " + accountId);
            return true;
        }
        return false;
    }

    /**
     * Apply monthly interest to all active savings accounts.
     */
    public void processMonthlyInterest() {
        for (Account account : accounts.values()) {
            if (account.isActive() && account.getType() == AccountType.SAVINGS) {
                account.applyMonthlyInterest();
            }
        }
        Logger.log("INFO", "Monthly interest processing complete");
    }

    /**
     * Get total bank holdings across all accounts.
     */
    public double getTotalHoldings() {
        double total = 0;
        for (Account account : accounts.values()) {
            if (account.isActive()) {
                total += account.getBalance();
            }
        }
        return total;
    }

    /**
     * Main entry point.
     */
    public static void main(String[] args) {
        BankingApp app = new BankingApp();

        // Create some test accounts
        Account savings = app.createAccount("Alice", 5000.0, AccountType.SAVINGS);
        Account checking = app.createAccount("Bob", 3000.0, AccountType.CHECKING);

        // Do some operations
        savings.deposit(1000.0);
        checking.withdraw(500.0);
        savings.transfer(checking, 200.0);

        // Monthly interest
        app.processMonthlyInterest();

        // Print summary
        Logger.log("INFO", "Total holdings: $" + app.getTotalHoldings());
    }
}
