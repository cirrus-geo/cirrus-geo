const versions = window.location.origin + '/versions.txt';

const makeVersionElement = (version) => {
  const path = window.location.pathname.split('/').slice(2,).join('/')
  const versionURL = window.location.origin + '/' + version + '/' + path
  return `<dd><a href="${versionURL}">${version}</a></dd>`
}

fetch(versions)
  .then(response => {
    return response.text()
  })
  .then(data => data.split('\n').map(makeVersionElement).join('\n'))
  .then(data => {
    const versionsList = document.querySelector('#versions-list')
    const html = versionsList.innerHTML
    versionsList.innerHTML = html + '\n' + data
  });
