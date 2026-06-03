package com.cumuluscycles.agentportal.web;

import com.cumuluscycles.agentportal.sda.SdaClient;
import com.cumuluscycles.agentportal.sda.dto.LoginRequest;
import com.cumuluscycles.agentportal.sda.dto.TokenResponse;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final SdaClient sda;

    public AuthController(SdaClient sda) {
        this.sda = sda;
    }

    @PostMapping("/login")
    public TokenResponse login(@Valid @RequestBody LoginRequest body) {
        return sda.login(body);
    }
}
