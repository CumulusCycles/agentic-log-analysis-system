package com.cumuluscycles.agentportal.web;

import com.cumuluscycles.agentportal.auth.AuthAttributes;
import com.cumuluscycles.agentportal.sda.SdaClient;
import com.cumuluscycles.agentportal.sda.dto.ClaimDetail;
import com.cumuluscycles.agentportal.sda.dto.ClaimOut;
import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/claims")
public class ClaimsController {

    private final SdaClient sda;

    public ClaimsController(SdaClient sda) {
        this.sda = sda;
    }

    @GetMapping
    public List<ClaimOut> list(HttpServletRequest request) {
        String bearer = (String) request.getAttribute(AuthAttributes.BEARER);
        return sda.getClaims(bearer);
    }

    @GetMapping("/{id}")
    public ClaimDetail detail(@PathVariable String id, HttpServletRequest request) {
        String bearer = (String) request.getAttribute(AuthAttributes.BEARER);
        return sda.getClaim(id, bearer);
    }
}
