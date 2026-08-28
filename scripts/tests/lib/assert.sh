assert_eq() {
  local expected="$1" actual="$2" msg="$3"
  if [[ "$expected" != "$actual" ]]; then
    echo "FAIL: $msg (expected=$expected actual=$actual)" >&2
    exit 1
  fi
  echo "PASS: $msg"
}
