"""
Stress test load shape: stepped ramp from 100 -> 2000 users over ~10 minutes.

Five plateaus of 2 minutes each makes it trivial to pinpoint the breaking
point in the Locust HTML report — every plateau is a stable measurement
window, and you can see exactly which step first crosses the 5% error rate
threshold the plan calls out.

Stage 1:  0:00 - 2:00   100 users
Stage 2:  2:00 - 4:00   250 users
Stage 3:  4:00 - 6:00   500 users
Stage 4:  6:00 - 8:00  1000 users
Stage 5:  8:00 - 10:00 2000 users

Run with:
    locust -f tests/load/stress_shape.py FlightSearchUser \
        --host https://d360csr5wvytoh.cloudfront.net \
        --headless --html reports/load/stress.html \
        --csv reports/load/stress
"""

# Import the user classes from the main locustfile so this shape can drive any of them.
from locustfile import (
    FlightSearchUser,
    BookingUser,
    BaggageTrackingUser,
    EndToEndUser,
)

from locust import LoadTestShape


class StressRamp(LoadTestShape):
    stages = [
        {"duration": 120,  "users": 100,  "spawn_rate": 25},
        {"duration": 240,  "users": 250,  "spawn_rate": 25},
        {"duration": 360,  "users": 500,  "spawn_rate": 25},
        {"duration": 480,  "users": 1000, "spawn_rate": 50},
        {"duration": 600,  "users": 2000, "spawn_rate": 50},
    ]

    def tick(self):
        elapsed = self.get_run_time()
        for stage in self.stages:
            if elapsed < stage["duration"]:
                return stage["users"], stage["spawn_rate"]
        return None  # end test
