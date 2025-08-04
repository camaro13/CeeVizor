
set pagination off
start
while $pc
  printf "##STEP##\n"
  info locals
  list
  next
end
quit
