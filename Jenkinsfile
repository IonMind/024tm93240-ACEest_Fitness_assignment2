pipeline {
    agent any

    options {
        disableConcurrentBuilds()
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
    }

    triggers {
        pollSCM('H/5 * * * *')
    }

    parameters {
        string(name: 'SONAR_ORGANIZATION', defaultValue: 'ionmind', description: 'SonarQube Cloud organization key')
        string(name: 'SONAR_PROJECT_KEY', defaultValue: 'IonMind_024tm93240-ACEest_Fitness_assignment2', description: 'SonarQube Cloud project key')
        string(name: 'SONAR_REGION', defaultValue: '', description: 'Cloud region; leave empty for EU')
    }

    environment {
        TEST_IMAGE = 'aceest:jenkins-test'
        IMAGE_REPOSITORY = '2024tm93240/2024tm93240_ace_fitness'
        KUBE_NAMESPACE = 'aceest'
    }

    stages {
        stage('Build test image') {
            steps {
                sh '''
                    docker build -t "$TEST_IMAGE" .
                '''
            }
        }

        stage('Test in container') {
            steps {
                                sh '''
                                        docker run --rm --user "$(id -u):$(id -g)" -e ACEEST_ENV=development \
                                            --mount "type=bind,source=$WORKSPACE,target=/workspace" \
                                            --workdir /workspace "$TEST_IMAGE" python -m pytest \
                                            -p no:cacheprovider --cov=app --cov-report=term-missing \
                      --cov-report=xml:coverage.xml --junitxml=test-results.xml
                '''
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: 'test-results.xml'
                    archiveArtifacts allowEmptyArchive: true, artifacts: 'coverage.xml'
                }
            }
        }

        stage('SonarQube Cloud quality gate') {
            when { branch 'main' }
            steps {
                script {
                    def scannerHome = tool 'sonar-scanner'
                    withEnv(["SCANNER_HOME=${scannerHome}"]) {
                        withSonarQubeEnv(installationName: 'sonarqube-cloud', credentialsId: 'sonarqube-token') {
                            withCredentials([string(credentialsId: 'sonarqube-token', variable: 'SONAR_TOKEN')]) {
                                sh '''
                                    set +x
                                    : "${SONAR_ORGANIZATION:?SonarQube organization is required}"
                                    : "${SONAR_PROJECT_KEY:?SonarQube project key is required}"
                                    set -- "-Dsonar.organization=$SONAR_ORGANIZATION" "-Dsonar.projectKey=$SONAR_PROJECT_KEY" '-Dsonar.qualitygate.wait=true'
                                    if [ -n "$SONAR_REGION" ]; then
                                        set -- "$@" "-Dsonar.region=$SONAR_REGION"
                                    fi
                                    "$SCANNER_HOME/bin/sonar-scanner" "$@"
                                '''
                            }
                        }
                    }
                }
            }
        }

        stage('Publish image') {
            when { branch 'main' }
            steps {
                script {
                    env.RELEASE_IMAGE = "${env.IMAGE_REPOSITORY}:${env.GIT_COMMIT}-${env.BUILD_NUMBER}"
                }
                withCredentials([usernamePassword(credentialsId: 'dockerhub', usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASSWORD')]) {
                    sh '''
                        set +x
                        export DOCKER_CONFIG="$(mktemp -d)"
                        trap 'rm -rf "$DOCKER_CONFIG"' 0
                        printf '%s' "$DOCKER_PASSWORD" | docker login --username "$DOCKER_USER" --password-stdin
                        docker tag "$TEST_IMAGE" "$RELEASE_IMAGE"
                        docker push "$RELEASE_IMAGE"
                    '''
                }
            }
        }

        stage('Deploy to Minikube') {
            when { branch 'main' }
            steps {
                sh '''
                    kubectl config get-contexts minikube -o name
                    kubectl --context=minikube -n "$KUBE_NAMESPACE" get secret aceest-secrets -o name
                    previous_deployment=$(kubectl --context=minikube -n "$KUBE_NAMESPACE" get deployment aceest --ignore-not-found -o name)
                    manifest=$(mktemp)
                    trap 'rm -f "$manifest"' 0
                    kubectl kustomize k8s/base > "$manifest"
                    sed "s|image: aceest:local-test|image: $RELEASE_IMAGE|" "$manifest" > "$manifest.updated"
                    trap 'rm -f "$manifest" "$manifest.updated"' 0
                    if kubectl --context=minikube -n "$KUBE_NAMESPACE" apply -f "$manifest.updated" &&
                       kubectl --context=minikube -n "$KUBE_NAMESPACE" rollout status deployment/aceest --timeout=120s &&
                       kubectl --context=minikube -n "$KUBE_NAMESPACE" exec deployment/aceest -- python -c "import urllib.request; urllib.request.urlopen('http://aceest/readyz', timeout=10).read()"; then
                        exit 0
                    fi
                    if [ -n "$previous_deployment" ]; then
                        kubectl --context=minikube -n "$KUBE_NAMESPACE" rollout undo deployment/aceest || echo 'Rollback command failed' >&2
                        kubectl --context=minikube -n "$KUBE_NAMESPACE" rollout status deployment/aceest --timeout=120s || echo 'Rollback did not become ready' >&2
                    fi
                    exit 1
                '''
            }
        }
    }
}