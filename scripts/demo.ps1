param([string]$BaseUrl = 'http://127.0.0.1:8000')
$ErrorActionPreference = 'Stop'
$departure = (Get-Date).ToUniversalTime().Date.AddDays(30)
$returning = $departure.AddDays(7)
$headers = @{}
if ($env:TRAVEL_API_KEY) { $headers.Authorization = 'Bearer ' + $env:TRAVEL_API_KEY }
$provider = Invoke-RestMethod -Uri ($BaseUrl + '/v1/providers') -Headers $headers
if ($provider.selected -ne 'mock') {
    throw 'This demo uses synthetic example trips and requires mock mode. Use the single-search probe for supplier checks.'
}
$brief = @{
    origin = 'LHR'; destination = 'LIS'
    departure_date = $departure.ToString('yyyy-MM-dd')
    return_date = $returning.ToString('yyyy-MM-dd')
    adults = 2; budget_amount = '4000.00'; budget_currency = 'USD'; flexibility_days = 1
    stay_location = @{ latitude = 38.7223; longitude = -9.1393; radius_km = 3 }
    check_in_date = $departure.ToString('yyyy-MM-dd')
    check_out_date = $returning.ToString('yyyy-MM-dd')
} | ConvertTo-Json -Depth 5
$trip = Invoke-RestMethod -Uri ($BaseUrl + '/v1/trips') -Method Post -Headers $headers -ContentType 'application/json' -Body $brief
$result = Invoke-RestMethod -Uri ($BaseUrl + '/v1/trips/' + $trip.trip_id + '/search') -Method Post -Headers $headers -ContentType 'application/json' -Body '{"date_offsets":[-1,0,1]}'
$result | ConvertTo-Json -Depth 15
