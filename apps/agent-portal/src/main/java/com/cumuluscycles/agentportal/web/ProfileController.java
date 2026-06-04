package com.cumuluscycles.agentportal.web;

import com.cumuluscycles.agentportal.auth.AuthAttributes;
import com.cumuluscycles.agentportal.sda.SdaClient;
import com.cumuluscycles.agentportal.sda.dto.UserOut;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/profile")
public class ProfileController {

    private static final Logger log = LoggerFactory.getLogger(ProfileController.class);

    private final SdaClient sda;

    public ProfileController(SdaClient sda) {
        this.sda = sda;
    }

    @GetMapping("/me")
    public UserOut me(HttpServletRequest request) {
        String userId = (String) request.getAttribute(AuthAttributes.USER_ID);
        String bearer = (String) request.getAttribute(AuthAttributes.BEARER);
        UserOut user = sda.getUser(userId, bearer);
        log.info("profile_fetched user_id={}", userId);
        return user;
    }
}
