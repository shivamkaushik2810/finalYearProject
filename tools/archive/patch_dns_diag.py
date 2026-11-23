import pathlib

p = pathlib.Path(".github/workflows/weekly_reports.yml")
src = p.read_text()

old = (
    "          else:\n"
    "              print(\"DNS resolves: False after 6 attempts -\", last)\n"
    "              raise SystemExit(1)\n"
)
new = (
    "          else:\n"
    "              print(\"DNS resolves: False after 6 attempts -\", last)\n"
    "              for ctl in (\"github.com\", \"supabase.com\", \"api.supabase.com\"):\n"
    "                  try:\n"
    "                      socket.getaddrinfo(ctl, 443)\n"
    "                      print(f\"control {ctl}: resolves\")\n"
    "                  except Exception as e:\n"
    "                      print(f\"control {ctl}: FAILS - {e}\")\n"
    "              try:\n"
    "                  socket.getaddrinfo(host, 443, socket.AF_INET)\n"
    "                  print(\"project host over IPv4 only: resolves\")\n"
    "              except Exception as e:\n"
    "                  print(f\"project host over IPv4 only: FAILS - {e}\")\n"
    "              try:\n"
    "                  ns = [l.split()[1] for l in open('/etc/resolv.conf') if l.startswith('nameserver')]\n"
    "                  print('runner nameservers:', ns)\n"
    "              except Exception as e:\n"
    "                  print('could not read resolv.conf:', e)\n"
    "              raise SystemExit(1)\n"
)
if src.count(old) != 1:
    raise SystemExit(f"Expected 1 match, found {src.count(old)} - no changes made")
p.write_text(src.replace(old, new))
print("patched")
