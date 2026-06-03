package com.cumuluscycles.agentportal.web;

import com.cumuluscycles.agentportal.sda.SdaException;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(SdaException.class)
    public ResponseEntity<Map<String, String>> handleSda(SdaException ex) {
        return ResponseEntity.status(ex.status()).body(Map.of("detail", ex.detail()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> handleValidation(MethodArgumentNotValidException ex) {
        String detail = ex.getBindingResult().getFieldErrors().stream()
                .findFirst()
                .map(err -> err.getField() + ": " + err.getDefaultMessage())
                .orElse("invalid request");
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(Map.of("detail", detail));
    }
}
