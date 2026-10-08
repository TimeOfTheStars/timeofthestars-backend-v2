import pytest


@pytest.mark.parametrize('stage', ['quarterfinal', 'semifinal', 'final', 'third_place'])
async def test_playoff_stage_roundtrip_and_standings(client, auth, stage):
    teams = []
    for name in ['Альфа', 'Бета']:
        response = await client.post('/api/v1/teams', json={'name': name}, headers=auth)
        assert response.status_code == 201
        teams.append(response.json()['id'])
    response = await client.post(
        '/api/v1/competitions',
        json={'type': 'tournament', 'name': 'Кубок', 'start_date': '2026-10-08'},
        headers=auth,
    )
    competition_id = response.json()['id']
    for team_id in teams:
        await client.post(
            f'/api/v1/competitions/{competition_id}/teams',
            json={'team_id': team_id}, headers=auth,
        )
    response = await client.post('/api/v1/games', json={
        'competition_id': competition_id, 'team_a_id': teams[0], 'team_b_id': teams[1],
        'date': '2026-10-08', 'stage': stage, 'score_team_a': 3, 'score_team_b': 1,
    }, headers=auth)
    assert response.status_code == 201, response.text
    game_id = response.json()['id']
    assert response.json()['stage'] == stage
    assert (await client.get(f'/api/v1/games/{game_id}')).json()['stage'] == stage
    standings = (await client.get(f'/api/v1/competitions/{competition_id}/standings')).json()
    assert all(row['games'] == 0 and row['points'] == 0 for row in standings)
    await client.post('/admin/login', data={'username': 'admin', 'password': 'admin'})
    page = await client.get(f'/admin/games/{game_id}/edit')
    assert page.status_code == 200
    assert 'value="third_place"' in page.text and 'За 3 место' in page.text
    response = await client.post(f'/admin/games/{game_id}/edit', data={
        'team_a_id': str(teams[0]), 'team_b_id': str(teams[1]),
        'date': '2026-10-08', 'stage': 'third_place',
    }, follow_redirects=False)
    assert response.status_code == 303, response.text
    assert (await client.get(f'/api/v1/games/{game_id}')).json()['stage'] == 'third_place'
    page = await client.get(f'/admin/competitions/{competition_id}')
    assert page.status_code == 200 and 'За 3 место' in page.text
