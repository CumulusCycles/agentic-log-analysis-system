package com.cumuluscycles.agentportal.web;

import com.cumuluscycles.agentportal.auth.AuthAttributes;
import com.cumuluscycles.agentportal.sda.SdaClient;
import com.cumuluscycles.agentportal.sda.dto.ClaimDetail;
import com.cumuluscycles.agentportal.sda.dto.ClaimOut;
import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/claims")
public class ClaimsController {

    private static final Logger log = LoggerFactory.getLogger(ClaimsController.class);

    private final SdaClient sda;

    public ClaimsController(SdaClient sda) {
        this.sda = sda;
    }

    @GetMapping
    public List<ClaimOut> list(HttpServletRequest request) {
        String bearer = (String) request.getAttribute(AuthAttributes.BEARER);
        List<ClaimOut> claims = sda.getClaims(bearer);
        log.info("claims_fetched count={}", claims.size());
        return claims;
    }

    @GetMapping("/{id}")
    public ClaimDetail detail(@PathVariable String id, HttpServletRequest request) {
        String bearer = (String) request.getAttribute(AuthAttributes.BEARER);
        ClaimDetail claim = sda.getClaim(id, bearer);
        log.info("claim_fetched claim_id={} current_status={}", id, claim.currentStatus());
        return claim;
    }
}
