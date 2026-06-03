package com.cumuluscycles.agentportal.sda;

public class SdaException extends RuntimeException {

    private final int status;
    private final String detail;

    public SdaException(int status, String detail) {
        super(detail);
        this.status = status;
        this.detail = detail;
    }

    public int status() {
        return status;
    }

    public String detail() {
        return detail;
    }
}
