version 1.1

workflow hello {
  input {
    String name
    Int times = 1
  }

  call greet {
    input:
      name = name,
      times = times
  }

  output {
    File greeting = greet.greeting
  }
}

task greet {
  input {
    String name
    Int times
  }

  command <<<
    for i in $(seq ~{times}); do
      echo "Hello, ~{name}!"
    done > greeting.txt
  >>>

  output {
    File greeting = "greeting.txt"
  }

  runtime {
    docker: "ubuntu:24.04"
  }
}
