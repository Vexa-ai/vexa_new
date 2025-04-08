#!/usr/bin/env python3

import subprocess
import json

def get_transcript_segments(native_meeting_id, platform, container_name="vexa-postgres-1"):
    # Query to get meeting ID
    meeting_query = f"""
    SELECT id FROM meetings 
    WHERE native_meeting_id = '{native_meeting_id}' 
    AND platform = '{platform}'
    """
    
    # Run docker exec to execute the query
    cmd = [
        "docker", "exec", container_name, 
        "psql", "-U", "postgres", "-d", "vexa", 
        "-t", "-c", meeting_query
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result)
    # meeting_id = result.stdout.strip()
    
    # if not meeting_id:
    #     return []
    
    # # Query to get transcript segments
    # segments_query = f"""
    # SELECT row_to_json(t) FROM (
    #     SELECT * FROM transcript_segments 

    #     ORDER BY start_time
    # ) t
    # """
    
    # cmd = [
    #     "docker", "exec", container_name, 
    #     "psql", "-U", "postgres", "-d", "vexa", 
    #     "-t", "-c", segments_query
    # ]
    
    # result = subprocess.run(cmd, capture_output=True, text=True)
    # segments = []
    
    # for line in result.stdout.strip().split("\n"):
    #     if line.strip():
    #         segments.append(json.loads(line))
    
    # return segments

if __name__ == "__main__":
    segments = get_transcript_segments("zjz-gmju-mfo", "google_meet")
   # print(f"Found {len(segments)} transcript segments") 
    
    
#chmod +x docker_db_check.py && python docker_db_check.py