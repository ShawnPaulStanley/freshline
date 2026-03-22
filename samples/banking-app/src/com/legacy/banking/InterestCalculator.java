package com.legacy.banking;

/**
 * Interest rate calculator utility.
 * Provides rates based on account type.
 * 
 * Last updated: 2008
 * Author: Legacy Team
 */
public class InterestCalculator {

    // Interest rates - these should probably be in a config file
    private static final double SAVINGS_RATE = 0.04;
    private static final double CHECKING_RATE = 0.01;
    private static final double FIXED_DEPOSIT_RATE = 0.07;
    private static final double DEFAULT_RATE = 0.02;

    /**
     * Get the annual interest rate for a given account type.
     */
    public static double getRate(AccountType type) {
        switch (type) {
            case SAVINGS:
                return SAVINGS_RATE;
            case CHECKING:
                return CHECKING_RATE;
            case FIXED_DEPOSIT:
                return FIXED_DEPOSIT_RATE;
            default:
                return DEFAULT_RATE;
        }
    }

    /**
     * Calculate compound interest over N years.
     * Used by the old reporting module. Probably dead code.
     */
    public static double compoundInterest(double principal, double rate, int years) {
        return principal * Math.pow(1 + rate, years) - principal;
    }

    /**
     * Simple interest calculation. Also probably dead.
     */
    public static double simpleInterest(double principal, double rate, int years) {
        return principal * rate * years;
    }
}
