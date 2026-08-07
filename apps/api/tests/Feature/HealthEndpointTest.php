<?php

namespace Tests\Feature;

use Tests\TestCase;

class HealthEndpointTest extends TestCase
{
    public function test_health_endpoint_reports_ok_when_database_reachable(): void
    {
        $response = $this->getJson('/api/v1/health');

        $response->assertStatus(200)
            ->assertJson([
                'status' => 'ok',
                'service' => 'my-pain-radar-api',
                'checks' => [
                    'app' => true,
                    'database' => true,
                ],
            ]);
    }
}
