package com.hiskjuc.videodownloader

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.hiskjuc.videodownloader.ui.theme.VideoDownloaderTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        // Inicialização do runtime Python do Chaquopy
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        setContent {
            VideoDownloaderTheme {
                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    PoCScreen(modifier = Modifier.padding(innerPadding))
                }
            }
        }
    }
}

@Composable
fun PoCScreen(modifier: Modifier = Modifier) {
    var url by remember { mutableStateOf("https://www.youtube.com/watch?v=BaW_jenozKc") }
    var isLoading by remember { mutableStateOf(false) }
    var resultText by remember { mutableStateOf("Aguardando extração...") }
    val coroutineScope = rememberCoroutineScope()

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        OutlinedTextField(
            value = url,
            onValueChange = { url = it },
            label = { Text("URL do Vídeo") },
            modifier = Modifier.fillMaxWidth(),
            enabled = !isLoading,
            singleLine = true
        )

        Button(
            onClick = {
                if (url.isNotBlank()) {
                    isLoading = true
                    resultText = "Consultando metadados...\n(Pode demorar no 1º acesso)"

                    coroutineScope.launch {
                        resultText = withContext(Dispatchers.IO) {
                            try {
                                val py = Python.getInstance()
                                val module = py.getModule("yt_extractor")
                                module.callAttr("get_metadata", url).toString()
                            } catch (e: Exception) {
                                "Erro na ponte Chaquopy: ${e.localizedMessage}"
                            }
                        }
                        isLoading = false
                    }
                }
            },
            enabled = !isLoading && url.isNotBlank(),
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Extrair Metadados")
        }

        if (isLoading) {
            CircularProgressIndicator()
        }

        Text(
            text = resultText,
            style = MaterialTheme.typography.bodyLarge,
            modifier = Modifier.fillMaxWidth()
        )
    }
}